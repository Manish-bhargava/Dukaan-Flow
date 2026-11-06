from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from seed.run_seed import seed_id

SHARMA = seed_id("retailer", "sharma")
GUPTA = seed_id("retailer", "gupta")


def _products_by_sku(client, retailer_id):
    response = client.get(f"/api/v1/dev/retailers/{retailer_id}/products")
    assert response.status_code == 200
    return {p["sku"]: p for p in response.json()["data"]["products"]}


def test_db_status_reports_connected(client):
    body = client.get("/api/v1/dev/db-status").json()
    assert body["success"] is True
    assert body["data"]["status"] == "connected"
    assert body["data"]["migration_revision"] is not None


def test_seed_summary_counts(client):
    data = client.get("/api/v1/dev/seed-summary").json()["data"]
    assert data["users"] == 6
    assert data["users_by_role"] == {"ADMIN": 1, "ORDER_DESK": 1, "SALESMAN": 2, "RETAILER": 2}
    assert (data["orders"], data["orders_by_status"], data["otp_verifications"]) == (0, {}, 0)
    assert (data["retailers"], data["products"], data["schemes"], data["inventory_records"]) == (
        5,
        10,
        3,
        10,
    )


def test_products_come_from_database(client):
    data = client.get("/api/v1/dev/products").json()["data"]
    tea = next(p for p in data if p["sku"] == "SKU-TE-250")
    assert len(data) == 10
    assert tea["stock_cases"] == "0.000"
    assert tea["category"] == "Tea"


def test_retailers_include_salesman_and_available_credit(client):
    data = client.get("/api/v1/dev/retailers").json()["data"]
    sharma = next(r for r in data if r["id"] == str(SHARMA))
    assert sharma["assigned_salesman"]["name"] == "Sunil Yadav"
    assert sharma["credit"] == {
        "credit_limit": "50000.00",
        "current_outstanding": "35000.00",
        "available_credit": "15000.00",
    }


def test_retailer_specific_prices_differ_between_retailers(client):
    sharma = _products_by_sku(client, SHARMA)
    gupta = _products_by_sku(client, GUPTA)
    assert sharma["SKU-BS-075"]["price"]["dealer_price"] == "8.10"
    assert gupta["SKU-BS-075"]["price"]["dealer_price"] == "7.94"
    assert sharma["SKU-DT-1KG"]["price"]["dealer_price"] == "101.50"
    assert gupta["SKU-DT-1KG"]["price"]["dealer_price"] == "99.47"


def test_expired_price_is_not_used(client):
    # Sharma also has an expired ₹7.90 biscuit price (2025-07-01 to 2026-01-01).
    price = _products_by_sku(client, SHARMA)["SKU-BS-075"]["price"]
    assert price["dealer_price"] == "8.10"
    assert price["effective_to"] is None


def test_only_currently_active_schemes_are_returned(client):
    products = _products_by_sku(client, SHARMA)
    [biscuit_scheme] = products["SKU-BS-075"]["schemes"]
    [detergent_scheme] = products["SKU-DT-1KG"]["schemes"]
    assert (biscuit_scheme["scheme_type"], biscuit_scheme["min_quantity"]) == ("FREE_GOODS", "10.000")
    assert biscuit_scheme["free_quantity"] == "1.000"
    assert detergent_scheme["scheme_type"] == "SLAB_DISCOUNT"
    assert detergent_scheme["discount_percentage"] == "3.00"
    assert products["SKU-NS-070"]["schemes"] == []  # its scheme expired on 2026-07-01


def test_unknown_retailer_returns_not_found(client):
    response = client.get("/api/v1/dev/retailers/00000000-0000-0000-0000-000000000000/products")
    assert response.status_code == 404
    assert response.json()["error_code"] == "RESOURCE_NOT_FOUND"


def test_invalid_retailer_id_returns_validation_error(client):
    response = client.get("/api/v1/dev/retailers/not-a-uuid/products")
    assert response.status_code == 422
    assert response.json()["error_code"] == "VALIDATION_ERROR"


def test_dev_endpoints_are_not_mounted_outside_development():
    production_app = create_app(Settings(_env_file=None,
        ENVIRONMENT="production", JWT_SECRET_KEY="p" * 48,
        EMAIL_PROVIDER="brevo", BREVO_API_KEY="k", BREVO_SENDER_EMAIL="login@example.com",
    ))
    response = TestClient(production_app).get("/api/v1/dev/db-status")
    assert response.status_code == 404



# ---------------------------------------------------------------- endpoints over demo activity

import pytest  # noqa: E402

from seed.demo_activity import run_demo_activity  # noqa: E402


@pytest.fixture
def demo(tx, tx_client):
    run_demo_activity(tx)
    return tx_client


def test_seed_summary_counts_demo_activity(demo):
    data = demo.get("/api/v1/dev/seed-summary").json()["data"]
    assert data["orders_by_status"] == {"APPROVED": 1, "PENDING": 1, "CREDIT_HOLD": 1, "REJECTED": 1}
    assert (data["order_corrections"], data["ai_extractions"], data["ai_extraction_items"]) == (1, 3, 6)


def test_users_endpoint_lists_all_roles(demo):
    users = demo.get("/api/v1/dev/users").json()["data"]
    assert {u["role"] for u in users} == {"ADMIN", "ORDER_DESK", "SALESMAN", "RETAILER"}
    assert all(u["retailer_id"] for u in users if u["role"] == "RETAILER")


def test_orders_list_and_status_filter(demo):
    orders = demo.get("/api/v1/dev/orders").json()["data"]
    assert sorted(o["order_number"] for o in orders) == [f"DF-DEMO-000{i}" for i in range(1, 5)]
    held = demo.get("/api/v1/dev/orders", params={"status": "CREDIT_HOLD"}).json()["data"]
    assert [o["order_number"] for o in held] == ["DF-DEMO-0003"]
    assert demo.get("/api/v1/dev/orders", params={"status": "BOGUS"}).status_code == 422


def test_order_detail_by_number_shows_items_and_corrections(demo):
    order = demo.get("/api/v1/dev/orders/DF-DEMO-0002").json()["data"]
    assert (order["status"], order["source"], order["grand_total"]) == ("PENDING", "AI", "11268.60")
    assert [(c["old_quantity"], c["new_quantity"]) for c in order["corrections"]] == [("2.000", "3.000")]
    assert order["stock_movements"] == [] and order["ledger_entries"] == []


def test_order_detail_by_uuid_shows_approval_records(demo):
    number_to_id = {o["order_number"]: o["id"] for o in demo.get("/api/v1/dev/orders").json()["data"]}
    order = demo.get(f"/api/v1/dev/orders/{number_to_id['DF-DEMO-0001']}").json()["data"]
    assert sorted(m["quantity"] for m in order["stock_movements"]) == ["-11.000", "-5.000"]
    assert [(e["transaction_type"], e["amount"]) for e in order["ledger_entries"]] == [("ORDER_DEBIT", order["grand_total"])]


def test_unknown_order_returns_404(demo):
    response = demo.get("/api/v1/dev/orders/DF-NOPE")
    assert (response.status_code, response.json()["error_code"]) == (404, "RESOURCE_NOT_FOUND")


def test_ai_extractions_show_confirmation_and_clarification(demo):
    all_extractions = demo.get("/api/v1/dev/ai-extractions").json()["data"]
    confirmed = sorted(e["order_number"] for e in all_extractions if e["extraction_status"] == "CONFIRMED")
    assert confirmed == ["DF-DEMO-0002", "DF-DEMO-0004"]  # Sharma's order; Jain's (salesman, later rejected)
    extractions = {e["extraction_status"]: e for e in all_extractions}
    assert extractions["PENDING"]["order_number"] is None
    assert any(i["unit"] is None and i["requires_clarification"] for i in extractions["PENDING"]["items"])


def test_inventory_shows_movements(demo):
    stock = {p["sku"]: p for p in demo.get("/api/v1/dev/inventory").json()["data"]}
    assert stock["SKU-BS-075"]["stock_cases"] == "329.000"
    assert stock["SKU-DT-500"]["stock_cases"] == "52.000"
    assert [m["movement_type"] for m in stock["SKU-BS-075"]["movements"]] == ["RESTOCK", "ORDER_DEDUCTION"]


def test_retailer_credit_shows_ledger(demo):
    credit = demo.get(f"/api/v1/dev/retailers/{GUPTA}/credit").json()["data"]
    assert {e["transaction_type"] for e in credit["ledger"]} == {"ADJUSTMENT", "ORDER_DEBIT", "PAYMENT_CREDIT"}
    assert credit["available_credit"] == "78041.59"
    assert demo.get("/api/v1/dev/retailers/00000000-0000-0000-0000-000000000000/credit").status_code == 404


def test_integrity_passes_on_seed_data(demo):
    data = demo.get("/api/v1/dev/integrity").json()["data"]
    assert data["all_passed"] is True
    assert len(data["checks"]) == 9


def test_integrity_reports_broken_data(demo, tx):
    from sqlalchemy import text

    tx.execute(text("UPDATE credit_accounts SET current_outstanding = current_outstanding + 1"
                    " WHERE retailer_id = :r"), {"r": GUPTA})
    data = demo.get("/api/v1/dev/integrity").json()["data"]
    failed = {c["name"]: c["problems"] for c in data["checks"] if not c["passed"]}
    assert failed == {"credit_ledger_matches_outstanding": ["Gupta General Store"]}
