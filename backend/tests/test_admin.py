"""Admin module: backend-enforced access, master data with audit, prices, schemes, stock,
credit / ordering pause, users and assignments, monitoring views and reports."""

import csv
import io
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from app.models import AuditLog, CreditAccount, Inventory, RetailerPrice, Scheme, StockMovement, User
from seed.run_seed import seed_id
from tests.conftest import place_open_order
from tests.test_orders_api import accepted, as_user, cart, err, ok  # noqa: F401  (as_user is a fixture)

BS075, DT1KG, TE250 = (seed_id("product", s) for s in ("SKU-BS-075", "SKU-DT-1KG", "SKU-TE-250"))
SHARMA = seed_id("retailer", "sharma")
SUNIL, DEEPAK = seed_id("user", "salesman_sunil"), seed_id("user", "salesman_deepak")
ADMIN = "admin"


def admin(as_user, method, url, status=200, **kw):
    return ok(as_user(ADMIN, method, f"/admin{url}", **kw), status)


def audit_actions(tx, entity_id=None):
    statement = select(AuditLog.action)
    if entity_id is not None:
        statement = statement.where(AuditLog.entity_id == str(entity_id))
    return list(tx.scalars(statement.order_by(AuditLog.created_at)))


NEW_RETAILER = {"shop_name": "Test Kirana", "owner_name": "Asha Test", "phone": "9876500001", "email": "asha.test@example.com",
                "address": "1 Test Road", "city": "Jabalpur", "credit_limit": "25000.00"}


# ---------------------------------------------------------------- access


GETS = ["/dashboard", "/order-desk", "/audit", "/ai-orders", "/sync", "/settings", "/retailers", f"/retailers/{SHARMA}",
        f"/retailers/{SHARMA}/credit-history", f"/retailers/{SHARMA}/prices", "/salesmen", f"/salesmen/{SUNIL}",
        "/users", f"/users/{SUNIL}", "/categories", "/brands", "/products", f"/products/{BS075}", "/schemes", "/stock",
        f"/stock/{BS075}/history", "/reports", "/reports/sales-by-date"]


@pytest.mark.parametrize("user", ["retailer_sharma", "salesman_sunil", "order_desk"])
@pytest.mark.parametrize("method,url,body", [
    ("GET", "/admin/dashboard", None), ("GET", "/admin/retailers", None), ("POST", "/admin/retailers", NEW_RETAILER),
    ("PATCH", f"/admin/retailers/{SHARMA}/credit", {"credit_limit": "1"}), ("POST", "/admin/users", {}),
    ("PUT", "/admin/prices", {}), ("POST", f"/admin/stock/{BS075}/adjust", {}), ("PUT", "/admin/settings", {}),
    ("GET", "/admin/reports/sales-by-date/csv", None), ("GET", "/admin/audit", None),
])
def test_admin_api_is_admin_only(as_user, user, method, url, body):
    assert err(as_user(user, method, url, json=body)) == (403, "FORBIDDEN")


@pytest.mark.parametrize("url", GETS)
def test_every_admin_view_loads(as_user, url):
    assert admin(as_user, "GET", url) is not None


# ---------------------------------------------------------------- retailers, credit, assignments


def test_create_retailer_with_login_credit_and_salesman(as_user, tx):
    created = admin(as_user, "POST", "/retailers", 201, json={**NEW_RETAILER, "salesman_id": str(SUNIL)})
    detail = admin(as_user, "GET", f"/retailers/{created['id']}")
    assert detail["salesman"]["name"] == "Sunil Yadav" and detail["credit"]["credit_limit"] == "25000.00"
    assert [(u["phone"], u["email"]) for u in detail["logins"]] == [("9876500001", "asha.test@example.com")]
    assert audit_actions(tx, created["id"]) == ["RETAILER_CREATED"]
    # the same mobile cannot be used twice
    assert err(as_user(ADMIN, "POST", "/admin/retailers", json=NEW_RETAILER)) == (409, "CONFLICT")
    listed = admin(as_user, "GET", "/retailers", params={"search": "9876500001"})["items"]
    assert [r["shop_name"] for r in listed] == ["Test Kirana"]


def test_deactivating_a_retailer_blocks_its_login_and_orders(as_user, tx):
    admin(as_user, "PATCH", f"/retailers/{SHARMA}", json={"is_active": False})
    login = tx.scalar(select(User).where(User.retailer_id == SHARMA))
    tx.refresh(login)
    assert login.is_active is False
    assert err(as_user("retailer_sharma", "GET", "/retailers/me")) == (403, "ACCOUNT_DISABLED")
    assert err(as_user("salesman_sunil", "POST", "/orders", json=cart((BS075, 1), retailer_id=str(SHARMA)))) == (
        403, "ORDERING_RESTRICTED")
    assert "RETAILER_DEACTIVATED" in audit_actions(tx, SHARMA)


def test_ordering_pause_blocks_every_channel_until_removed(as_user, tx):
    assert as_user(ADMIN, "PATCH", f"/admin/retailers/{SHARMA}/credit", json={"ordering_restricted": True}).status_code == 422
    admin(as_user, "PATCH", f"/retailers/{SHARMA}/credit", json={"ordering_restricted": True, "reason": "Cheque bounced"})
    assert err(as_user("retailer_sharma", "POST", "/orders", json=cart((BS075, 1)))) == (403, "ORDERING_RESTRICTED")
    assert err(as_user("salesman_sunil", "POST", "/orders", json=cart((BS075, 1), retailer_id=str(SHARMA)))) == (
        403, "ORDERING_RESTRICTED")
    quote = ok(as_user("retailer_sharma", "POST", "/orders/quote", json=cart((BS075, 1))))
    assert quote["ordering_restricted_reason"] == "Cheque bounced"
    me = ok(as_user("retailer_sharma", "GET", "/retailers/me"))
    assert me["can_place_orders"] is False and me["ordering_restricted_reason"] == "Cheque bounced"

    admin(as_user, "PATCH", f"/retailers/{SHARMA}/credit", json={"ordering_restricted": False})
    ok(as_user("retailer_sharma", "POST", "/orders", json=cart((BS075, 1))), 201)
    assert audit_actions(tx, SHARMA)[-2:] == ["ORDERING_RESTRICTED", "ORDERING_RESTORED"]


def test_credit_limit_change_is_enforced_and_audited(as_user, tx):
    admin(as_user, "PATCH", f"/retailers/{SHARMA}/credit", json={"credit_limit": "0"})
    assert err(as_user("retailer_sharma", "POST", "/orders", json=cart((BS075, 1)))) == (409, "CREDIT_LIMIT_EXCEEDED")
    history = admin(as_user, "GET", f"/retailers/{SHARMA}/credit-history")
    change = history["changes"][0]
    assert change["action"] == "CREDIT_LIMIT_CHANGED" and change["details"]["changes"]["credit_limit"]["to"] == "0"
    assert change["actor"]["role"] == "ADMIN" and history["ledger"]


def test_assignment_moves_retailers_and_refuses_inactive_salesman(as_user, tx):
    jain = seed_id("retailer", "jain")
    result = admin(as_user, "POST", "/assignments", json={"salesman_id": str(DEEPAK), "retailer_ids": [str(SHARMA), str(jain)]})
    assert len(result["changed"]) == 2
    deepak = admin(as_user, "GET", f"/salesmen/{DEEPAK}")
    assert {str(SHARMA), str(jain)} <= {r["id"] for r in deepak["retailers"]}
    entry = tx.scalar(select(AuditLog).where(AuditLog.action == "ASSIGNMENT_CHANGED", AuditLog.entity_id == str(SHARMA)))
    assert entry.details["changes"]["salesman"] == {"from": "Sunil Yadav", "to": "Deepak Verma"}
    # the old salesman no longer sees the shop
    assert err(as_user("salesman_sunil", "POST", "/orders", json=cart((BS075, 1), retailer_id=str(SHARMA))))[0] == 403
    # unassign, then a salesman with no shops can be deactivated; one with shops cannot
    assert err(as_user(ADMIN, "PATCH", f"/admin/users/{DEEPAK}", json={"is_active": False})) == (409, "CONFLICT")
    tx.execute(update(User).where(User.id == SUNIL).values(is_active=False))
    tx.commit()
    assert err(as_user(ADMIN, "POST", "/admin/assignments", json={"salesman_id": str(SUNIL), "retailer_ids": [str(jain)]})) == (
        409, "CONFLICT")


# ---------------------------------------------------------------- users


def test_staff_user_lifecycle_and_role_rules(as_user, tx):
    created = admin(as_user, "POST", "/users", 201, json={"name": "New Desk", "phone": "9876500002", "role": "ORDER_DESK",
                                                         "password": "Secret#123"})
    assert created["role"] == "ORDER_DESK" and created["has_password"] and "password_hash" not in created
    assert as_user(ADMIN, "POST", "/admin/users", json={"name": "R", "phone": "9876500003", "role": "RETAILER",
                                                        "password": "Secret#123"}).status_code == 422
    changed = admin(as_user, "PATCH", f"/users/{created['id']}", json={"role": "SALESMAN"})
    assert changed["role"] == "SALESMAN"
    admin(as_user, "POST", f"/users/{created['id']}/reset-password", json={"new_password": "Another#456"})
    me = seed_id("user", "admin")
    assert err(as_user(ADMIN, "PATCH", f"/admin/users/{me}", json={"is_active": False})) == (409, "CONFLICT")
    assert err(as_user(ADMIN, "PATCH", f"/admin/users/{me}", json={"role": "ORDER_DESK"})) == (409, "CONFLICT")
    retailer_login = tx.scalar(select(User.id).where(User.retailer_id == SHARMA))
    assert err(as_user(ADMIN, "POST", f"/admin/users/{retailer_login}/reset-password",
                       json={"new_password": "Another#456"})) == (409, "CONFLICT")
    actions = audit_actions(tx, created["id"])
    assert actions == ["USER_CREATED", "USER_ROLE_CHANGED", "PASSWORD_RESET"]
    assert all("Another" not in str(e.details) for e in tx.scalars(select(AuditLog)))


def test_deactivated_user_loses_access_immediately(as_user):
    desk = seed_id("user", "order_desk")
    admin(as_user, "PATCH", f"/users/{desk}", json={"is_active": False})
    assert err(as_user("order_desk", "GET", "/order-desk/summary")) == (403, "ACCOUNT_DISABLED")


# ---------------------------------------------------------------- catalogue, prices, schemes, stock


def test_product_with_default_price_reaches_every_catalogue(as_user, tx):
    category = seed_id("category", "Biscuits")
    body = {"sku": "sku-test-001", "name": "Test Cookies 50g", "brand": "Sunrise Foods", "category_id": str(category),
            "pack_size": "50g", "units_per_case": "48", "gst_rate": "18", "opening_stock": "30",
            "default_price": {"dealer_price": "5.50", "price_basis": "PIECE", "tax_inclusive": False}}
    created = admin(as_user, "POST", "/products", 201, json=body)
    product = admin(as_user, "GET", f"/products/{created['id']}")
    assert product["sku"] == "SKU-TEST-001" and product["stock"] == "30.000"
    assert product["default_price"]["dealer_price"] == "5.50" and product["movements"][0]["stock_after"] == "30.000"
    # no retailer-specific price: the default applies for every retailer
    catalogue = ok(as_user("retailer_sharma", "GET", "/products", params={"search": "Test Cookies"}))["items"]
    assert [p["price"]["dealer_price"] for p in catalogue] == ["5.50"]
    assert err(as_user(ADMIN, "POST", "/admin/products", json=body)) == (409, "CONFLICT")
    assert err(as_user(ADMIN, "POST", "/admin/products", json={**body, "sku": "X-2", "brand": "Nope"})) == (422, "VALIDATION_ERROR")


def test_price_changes_keep_history_and_never_touch_placed_orders(as_user, tx, ):
    tx.execute(update(CreditAccount).where(CreditAccount.retailer_id == SHARMA).values(credit_limit=Decimal("500000")))
    tx.commit()
    open_order = place_open_order(tx, "retailer_sharma", (BS075, 1))
    old_price = open_order.items[0].unit_price
    admin(as_user, "PUT", "/prices", json={"product_id": str(BS075), "retailer_id": str(SHARMA), "dealer_price": "9.99",
                                           "price_basis": "PIECE", "tax_inclusive": False})
    quote = ok(as_user("retailer_sharma", "POST", "/orders/quote", json=cart((BS075, 1))))
    assert quote["lines"][0]["unit_price"] == "9.99"
    assert ok(as_user("retailer_sharma", "GET", f"/orders/{open_order.id}"))["items"][0]["unit_price"] == str(old_price)
    rows = tx.scalars(select(RetailerPrice).where(RetailerPrice.retailer_id == SHARMA, RetailerPrice.product_id == BS075)
                      .order_by(RetailerPrice.effective_from)).all()
    assert rows[-2].effective_to is not None and rows[-1].dealer_price == Decimal("9.99") and rows[-1].created_by
    history = admin(as_user, "GET", f"/products/{BS075}")["price_history"]
    assert history[0]["dealer_price"] == "9.99" and history[0]["by"] == "Vivek Malhotra"
    # removing the retailer's own price: the product's default price (sample price 8.10) applies again
    admin(as_user, "DELETE", "/prices", params={"product_id": str(BS075), "retailer_id": str(SHARMA)})
    assert ok(as_user("retailer_sharma", "POST", "/orders/quote", json=cart((BS075, 1))))["lines"][0]["unit_price"] == "8.10"
    assert audit_actions(tx, BS075)[-2:] == ["PRICE_CHANGED", "PRICE_REMOVED"]


def test_schemes_cannot_overlap_and_apply_to_all_channels(as_user, tx):
    now = datetime.now(UTC)
    body = {"product_ids": [str(TE250)], "scheme_type": "SLAB_DISCOUNT", "min_quantity": "3", "discount_percentage": "4",
            "starts_at": (now - timedelta(minutes=1)).isoformat()}
    existing = tx.scalars(select(Scheme).where(Scheme.product_id == TE250, Scheme.is_active.is_(True))).all()
    for s in existing:
        s.is_active = False
    tx.commit()
    created = admin(as_user, "POST", "/schemes", 201, json=body)
    assert created[0]["description"] == "4% off on 3+" and created[0]["state"] == "active"
    assert err(as_user(ADMIN, "POST", "/admin/schemes", json={**body, "scheme_type": "FREE_GOODS", "free_quantity": "1",
                                                              "discount_percentage": "0"})) == (409, "SCHEME_CONFLICT")
    line = ok(as_user("retailer_sharma", "POST", "/orders/quote", json=cart((TE250, 3))))["lines"][0]
    assert line["scheme"]["description"] == "4% off on 3+"
    assert as_user(ADMIN, "POST", "/admin/schemes", json={**body, "discount_percentage": "0"}).status_code == 422
    # upcoming and expired views
    admin(as_user, "PATCH", f"/schemes/{created[0]['id']}", json={"ends_at": (now + timedelta(seconds=1)).isoformat()})
    upcoming = admin(as_user, "POST", "/schemes", 201, json={**body, "starts_at": (now + timedelta(days=5)).isoformat()})
    assert upcoming[0]["state"] == "upcoming"
    assert upcoming[0]["id"] in {s["id"] for s in admin(as_user, "GET", "/schemes", params={"state": "upcoming"})["items"]}


def test_stock_adjustments_record_before_after_user_and_reason(as_user, tx):
    before = tx.scalar(select(Inventory.stock_cases).where(Inventory.product_id == DT1KG))
    result = admin(as_user, "POST", f"/stock/{DT1KG}/adjust", json={"mode": "add", "quantity": "5", "reason": "Truck 42"})
    assert (Decimal(result["stock_before"]), Decimal(result["stock_after"])) == (before, before + 5)
    assert as_user(ADMIN, "POST", f"/admin/stock/{DT1KG}/adjust",
                   json={"mode": "remove", "quantity": str(before + 100), "reason": "x"}).status_code == 422
    admin(as_user, "POST", f"/stock/{DT1KG}/adjust", json={"mode": "set", "quantity": "2", "reason": "Stock count"})
    history = admin(as_user, "GET", f"/stock/{DT1KG}/history")
    assert [(h["stock_before"], h["stock_after"], h["reason"], h["by"]) for h in history[:2]] == [
        (f"{before + 5:.3f}", "2.000", "Stock count", "Vivek Malhotra"),
        (f"{before:.3f}", f"{before + 5:.3f}", "Truck 42", "Vivek Malhotra")]
    low = admin(as_user, "GET", "/stock", params={"stock": "low"})["items"]
    assert str(DT1KG) in {p["id"] for p in low}
    entry = tx.scalars(select(AuditLog).where(AuditLog.action == "STOCK_CHANGED").order_by(AuditLog.created_at.desc())).first()
    assert entry.details["new"] == "2.000" and entry.details["reason"] == "Stock count"
    # movements still add up to the stock
    total = sum(tx.scalars(select(StockMovement.quantity).where(StockMovement.product_id == DT1KG)))
    assert total == Decimal(2)


def test_category_and_brand_management(as_user, tx):
    brand = admin(as_user, "POST", "/brands", 201, json={"name": "Test Brand"})
    renamed = admin(as_user, "PATCH", f"/brands/{brand['id']}", json={"name": "Test Brand Two"})
    assert renamed["name"] == "Test Brand Two"
    sunrise = next(b for b in admin(as_user, "GET", "/brands") if b["name"] == "Sunrise Foods")
    admin(as_user, "PATCH", f"/brands/{sunrise['id']}", json={"name": "Sunrise Foods Ltd"})
    assert admin(as_user, "GET", f"/products/{BS075}")["brand"] == "Sunrise Foods Ltd"  # cascaded
    category = admin(as_user, "POST", "/categories", 201, json={"name": "Dairy"})
    admin(as_user, "PATCH", f"/categories/{category['id']}", json={"is_active": False})
    assert err(as_user(ADMIN, "POST", "/admin/categories", json={"name": "Dairy"})) == (409, "CONFLICT")


# ---------------------------------------------------------------- monitoring, reports, settings


def test_dashboard_order_desk_and_audit_views(as_user, tx):
    place_open_order(tx, "retailer_sharma", (BS075, 1))
    dash = admin(as_user, "GET", "/dashboard")
    assert dash["retailers_total"] >= 5 and dash["pending"] >= 1 and dash["recent_orders"]
    desk = admin(as_user, "GET", "/order-desk")
    assert desk["overview"]["pending_review"] >= 1 and "tally_not_exported" in desk
    admin(as_user, "POST", f"/stock/{DT1KG}/adjust", json={"mode": "add", "quantity": "1", "reason": "Audit test"})
    log = admin(as_user, "GET", "/audit", params={"source": "master", "entity_type": "stock"})["items"]
    assert log[0]["action"] == "STOCK_CHANGED" and log[0]["actor"]["name"] == "Vivek Malhotra"
    orders_log = admin(as_user, "GET", "/audit", params={"source": "orders"})["items"]
    assert orders_log and all(e["action"].startswith("ORDER_") for e in orders_log)


def test_sync_failures_are_visible_to_admin(as_user, tx):
    body = cart((BS075, 1), retailer_id=str(SHARMA), client_order_id="admin-test-fail-01", created_offline=True)
    admin(as_user, "PATCH", f"/retailers/{SHARMA}/credit", json={"ordering_restricted": True, "reason": "Audit"})
    assert err(as_user("salesman_sunil", "POST", "/orders", json=body)) == (403, "ORDERING_RESTRICTED")
    ok(as_user("salesman_sunil", "POST", "/salesman/sync-status",
               json={"pending_orders": 0, "failed_orders": 1, "pending_visits": 0, "last_error": "paused"}))
    data = admin(as_user, "GET", "/sync")
    failure = next(f for f in data["failures"] if f["client_order_id"] == "admin-test-fail-01")
    assert failure["error_code"] == "ORDERING_RESTRICTED" and failure["salesman"] == "Sunil Yadav"
    sunil = next(s for s in data["salesmen"] if s["salesman"]["name"] == "Sunil Yadav")
    assert sunil["sync"]["failed_orders"] == 1


@pytest.mark.parametrize("name", ["sales-by-date", "sales-by-retailer", "sales-by-salesman", "sales-by-product",
                                  "sales-by-category", "source-breakdown", "confirmed-vs-rejected", "top-retailers",
                                  "top-products", "salesman-performance", "low-stock", "credit-outstanding",
                                  "inactive-retailers"])
def test_reports_json_and_csv(as_user, tx, name):
    ok(as_user("retailer_sharma", "POST", "/orders", json=cart((BS075, 1))), 201)
    data = admin(as_user, "GET", f"/reports/{name}")
    assert data["columns"] and all(len(r) == len(data["columns"]) for r in data["rows"])
    response = as_user(ADMIN, "GET", f"/admin/reports/{name}/csv")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows[0] == data["columns"] and len(rows) - 1 == len(data["rows"])


def test_sales_report_matches_confirmed_orders(as_user):
    placed = accepted(as_user, "retailer_sharma", cart((BS075, 2)))
    today = datetime.now().strftime("%Y-%m-%d")
    by_retailer = admin(as_user, "GET", "/reports/sales-by-retailer", params={"from_date": today, "to_date": today})
    sharma = next(r for r in by_retailer["rows"] if r[0] == placed["retailer"]["shop_name"])
    assert Decimal(sharma[3]) >= Decimal(placed["grand_total"])
    assert err(as_user(ADMIN, "GET", "/admin/reports/nope")) == (422, "VALIDATION_ERROR")


def test_settings_are_validated_saved_and_used(as_user, tx):
    current = admin(as_user, "GET", "/settings")
    assert as_user(ADMIN, "PUT", "/admin/settings", json={**current, "low_stock_cases": -1}).status_code == 422
    admin(as_user, "PUT", "/settings", json={**current, "low_stock_cases": 100000, "business_name": "Test Traders"})
    dash = admin(as_user, "GET", "/dashboard")
    assert dash["business_name"] == "Test Traders" and dash["low_stock_threshold"] == 100000
    assert dash["low_stock_count"] == dash["products_active"]
    assert "SETTINGS_CHANGED" in audit_actions(tx)


def test_new_retailer_sees_the_whole_catalogue_at_default_prices(as_user, tx, tx_client):
    """A shop created by the Admin has no prices of its own: it orders at the default prices."""
    import uuid

    from app.core.security import create_access_token

    created = admin(as_user, "POST", "/retailers", 201, json=NEW_RETAILER)
    login = tx.scalar(select(User).where(User.retailer_id == uuid.UUID(created["id"])))
    token, _ = create_access_token(login)
    headers = {"Authorization": f"Bearer {token}"}
    catalogue = tx_client.get("/api/v1/products", params={"limit": 100}, headers=headers).json()["data"]
    assert catalogue["total"] >= 10
    biscuit = next(p for p in catalogue["items"] if p["sku"] == "SKU-BS-075")
    assert biscuit["price"]["dealer_price"] == "8.10"  # the sample dealer price
    quote = tx_client.post("/api/v1/orders/quote", json=cart((BS075, 10)), headers=headers).json()["data"]
    assert quote["lines"][0]["scheme"]["description"] == "Buy 10 get 1 free"
