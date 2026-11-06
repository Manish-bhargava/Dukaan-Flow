"""Order HTTP API: cart quote, order placement, snapshots, isolation, Order Desk actions,
Tally export. Uses the seeded data (Sharma gets exactly the sample dealer prices)."""

import csv
import io
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from app.core.security import create_access_token
from app.models import CreditAccount, Inventory, RetailerPrice, Scheme
from seed.run_seed import seed_id
from tests.conftest import place_open_order, seed_user

BS075, DT1KG, TE250 = (seed_id("product", s) for s in ("SKU-BS-075", "SKU-DT-1KG", "SKU-TE-250"))
SHARMA = seed_id("retailer", "sharma")


@pytest.fixture
def as_user(tx_client, tx):
    def call(key, method, url, **kw):
        token, _ = create_access_token(seed_user(tx, key))
        return tx_client.request(method, f"/api/v1{url}", headers={"Authorization": f"Bearer {token}"}, **kw)
    return call


def cart(*lines, **extra):
    return {"items": [{"product_id": str(p), "quantity": q, "unit": "case"} for p, q in lines], **extra}


def ok(response, status=200):
    assert response.status_code == status, response.json()
    return response.json()["data"]


def accepted(as_user, user_key, body):
    """Place an order as `user_key`, then the Order Desk accepts it (every order is reviewed)."""
    placed = ok(as_user(user_key, "POST", "/orders", json=body), 201)
    return ok(as_user("order_desk", "POST", f"/orders/{placed['id']}/approve", json={}))


def err(response):
    return response.status_code, response.json()["error_code"]


# ---------------------------------------------------------------- cart quote


def test_quote_applies_free_goods_25_cases_gives_2_free(as_user):
    data = ok(as_user("retailer_sharma", "POST", "/orders/quote", json=cart((BS075, 25))))
    [line] = data["lines"]
    assert Decimal(line["quantity"]) == 25 and Decimal(line["free_quantity"]) == 2
    assert line["scheme"]["description"] == "Buy 10 get 1 free"
    # ₹8.10 per piece x 96 per case x 25 cases, GST 5% extra.
    assert Decimal(line["unit_price"]) == Decimal("8.10") and line["price_basis"] == "PIECE"
    assert line["tax_inclusive"] is False
    assert Decimal(line["taxable_amount"]) == Decimal("19440.00")
    assert Decimal(line["gst_amount"]) == Decimal("972.00")
    assert Decimal(line["line_total"]) == Decimal("20412.00")
    assert line["stock_ok"] is True and data["can_order"] is True


@pytest.mark.parametrize("cases, pct, discount", [(4, "0", "0.00"), (5, "3", "304.50")])
def test_quote_slab_discount_boundary(as_user, cases, pct, discount):
    [line] = ok(as_user("retailer_sharma", "POST", "/orders/quote", json=cart((DT1KG, cases))))["lines"]
    assert Decimal(line["discount_percentage"]) == Decimal(pct)
    assert Decimal(line["discount_amount"]) == Decimal(discount)  # 5 x 20 x 101.50 = 10150 -> 3% = 304.50
    assert (line["scheme"] is None) == (cases < 5)


def test_quote_totals_are_sums_of_lines(as_user):
    data = ok(as_user("retailer_sharma", "POST", "/orders/quote", json=cart((BS075, 10), (DT1KG, 5))))
    lines, totals = data["lines"], data["totals"]
    for key in ("discount_amount", "taxable_amount", "gst_amount", "line_total"):
        total_key = {"discount_amount": "discount_total", "line_total": "grand_total"}.get(key, key)
        assert sum(Decimal(l[key]) for l in lines) == Decimal(totals[total_key])
    assert Decimal(totals["subtotal"]) - Decimal(totals["discount_total"]) == Decimal(totals["taxable_amount"])


def test_quote_reports_out_of_stock_instead_of_failing(as_user):
    data = ok(as_user("retailer_sharma", "POST", "/orders/quote", json=cart((TE250, 1))))
    assert data["lines"][0]["stock_ok"] is False and data["can_order"] is False


def test_quote_counts_free_cases_against_stock(as_user, tx):
    tx.execute(update(Inventory).where(Inventory.product_id == BS075).values(stock_cases=10))
    data = ok(as_user("retailer_sharma", "POST", "/orders/quote", json=cart((BS075, 10))))
    assert data["lines"][0]["stock_ok"] is False  # 10 paid + 1 free > 10 in stock


def test_frontend_prices_and_totals_are_ignored(as_user):
    honest = ok(as_user("retailer_sharma", "POST", "/orders/quote", json=cart((BS075, 10))))
    payload = cart((BS075, 10), grand_total="1.00", discount_total="9999")
    payload["items"][0].update(unit_price="0.01", discount_percentage="100", free_quantity="50")
    tampered = ok(as_user("retailer_sharma", "POST", "/orders", json=payload), 201)
    assert tampered["grand_total"] == honest["totals"]["grand_total"]
    assert Decimal(tampered["items"][0]["free_quantity"]) == 1


# ---------------------------------------------------------------- placing orders


def test_place_order_stores_price_scheme_and_gst_snapshots(as_user, tx):
    order = ok(as_user("retailer_sharma", "POST", "/orders", json=cart((BS075, 10), remarks="Morning")), 201)
    # Catalogue orders wait for the Order Desk like every other order.
    assert order["status"] == "PENDING" and order["source"] == "MANUAL" and order["remarks"] == "Morning"
    [item] = order["items"]
    assert (item["sku"], Decimal(item["paid_quantity"]), Decimal(item["free_quantity"])) == ("SKU-BS-075", 10, 1)
    assert item["scheme"]["description"] == "Buy 10 get 1 free" and item["tax_inclusive"] is False

    # Tomorrow the price doubles and the scheme is switched off: the order must not change.
    tx.execute(update(RetailerPrice).where(RetailerPrice.retailer_id == SHARMA, RetailerPrice.product_id == BS075)
               .values(dealer_price=Decimal("16.20")))
    tx.execute(update(Scheme).where(Scheme.product_id == BS075).values(is_active=False))
    later = ok(as_user("retailer_sharma", "GET", f"/orders/{order['id']}"))
    assert later["items"] == order["items"] and later["grand_total"] == order["grand_total"]
    # ...while a new quote uses the new terms.
    [line] = ok(as_user("retailer_sharma", "POST", "/orders/quote", json=cart((BS075, 10))))["lines"]
    assert Decimal(line["unit_price"]) == Decimal("16.20") and line["scheme"] is None


def test_retailer_order_over_available_credit_is_refused(as_user):
    response = as_user("retailer_sharma", "POST", "/orders", json=cart((BS075, 25)))  # 20,412 > 15,000
    assert err(response) == (409, "CREDIT_LIMIT_EXCEEDED")
    assert response.json()["details"] == {"grand_total": "20412.00", "available_credit": "15000.00"}


def test_out_of_stock_order_is_refused(as_user):
    assert err(as_user("retailer_sharma", "POST", "/orders", json=cart((TE250, 1)))) == (409, "INSUFFICIENT_STOCK")


@pytest.mark.parametrize("item", [
    {"quantity": 0, "unit": "case"},
    {"quantity": -2, "unit": "case"},
    {"quantity": 5, "unit": "piece"},  # not the order unit: refused, never converted
    {"quantity": 5},
])
def test_invalid_quantity_or_unit_is_refused(as_user, item):
    payload = {"items": [{"product_id": str(BS075), **item}]}
    assert as_user("retailer_sharma", "POST", "/orders", json=payload).status_code == 422


def test_duplicate_product_lines_and_empty_cart_are_refused(as_user):
    assert as_user("retailer_sharma", "POST", "/orders", json=cart((BS075, 1), (BS075, 2))).status_code == 422
    assert as_user("retailer_sharma", "POST", "/orders", json={"items": []}).status_code == 422


def test_retailer_cannot_order_for_another_shop(as_user):
    payload = cart((BS075, 1), retailer_id=str(seed_id("retailer", "gupta")))
    assert err(as_user("retailer_sharma", "POST", "/orders", json=payload)) == (403, "FORBIDDEN")


def test_order_desk_cannot_place_orders(as_user):
    assert err(as_user("order_desk", "POST", "/orders", json=cart((BS075, 1)))) == (403, "FORBIDDEN")


# ---------------------------------------------------------------- isolation


def test_retailers_only_see_their_own_orders(as_user):
    sharma_order = ok(as_user("retailer_sharma", "POST", "/orders", json=cart((BS075, 1))), 201)
    gupta_list = ok(as_user("retailer_gupta", "GET", "/orders", params={"limit": 100}))
    assert sharma_order["id"] not in {o["id"] for o in gupta_list["items"]}
    assert {o["retailer"]["shop_name"] for o in gupta_list["items"]} <= {"Gupta General Store"}
    assert err(as_user("retailer_gupta", "GET", f"/orders/{sharma_order['id']}")) == (403, "FORBIDDEN")


@pytest.mark.parametrize("method, path, body", [
    ("POST", "/hold", {"reason": "x"}),
    ("POST", "/approve", {}),
    ("POST", "/reject", {"reason": "x"}),
])
def test_retailer_cannot_use_order_desk_actions(as_user, method, path, body):
    order = ok(as_user("retailer_sharma", "POST", "/orders", json=cart((BS075, 1))), 201)
    assert err(as_user("retailer_sharma", method, f"/orders/{order['id']}{path}", json=body)) == (403, "FORBIDDEN")
    item_id = order["items"][0]["id"]
    response = as_user("retailer_sharma", "PATCH", f"/orders/{order['id']}/items/{item_id}", json={"new_quantity": 3, "reason": "x"})
    assert err(response) == (403, "FORBIDDEN")


def test_retailer_cannot_see_desk_summary_or_export(as_user):
    assert err(as_user("retailer_sharma", "GET", "/order-desk/summary")) == (403, "FORBIDDEN")
    assert err(as_user("retailer_sharma", "GET", "/exports/tally/orders.csv")) == (403, "FORBIDDEN")


def test_endpoints_require_login(tx_client):
    for method, url in [("GET", "/orders"), ("POST", "/orders/quote"), ("GET", "/exports/tally/orders.csv")]:
        assert tx_client.request(method, f"/api/v1{url}").status_code == 401


# ---------------------------------------------------------------- Order Desk workflow


def test_order_desk_review_correct_hold_confirm_and_export(as_user, tx):
    tx.execute(update(CreditAccount).where(CreditAccount.retailer_id == SHARMA).values(credit_limit=Decimal("100000")))
    tx.commit()
    open_order = place_open_order(tx, "retailer_sharma", (BS075, 10), (DT1KG, 4))  # e.g. AI-captured
    order_id = str(open_order.id)
    placed = ok(as_user("retailer_sharma", "GET", f"/orders/{order_id}"))
    assert placed["status"] == "PENDING"

    # Incoming queue: filter by status and search by shop name / order number.
    queue = ok(as_user("order_desk", "GET", "/orders", params={"status": ["PENDING", "CREDIT_HOLD", "ON_HOLD"],
                                                                 "search": "sharma"}))
    assert order_id in {o["id"] for o in queue["items"]}
    found = ok(as_user("order_desk", "GET", "/orders", params={"search": placed["order_number"]}))
    assert [o["id"] for o in found["items"]] == [order_id]
    counts = ok(as_user("order_desk", "GET", "/order-desk/summary"))
    assert counts["PENDING"] >= 1 and set(counts) == {"PENDING", "CREDIT_HOLD", "ON_HOLD", "CLARIFICATION_REQUIRED", "APPROVED", "REJECTED"}

    # Detail shows retailer info and line snapshots.
    detail = ok(as_user("order_desk", "GET", f"/orders/{order_id}"))
    assert detail["retailer"]["gstin"] == "23AAAPS1234A1Z5" and detail["ai"] is None

    # Correct detergent 4 -> 5 cases: re-priced with the slab discount, correction recorded.
    detergent = next(i for i in detail["items"] if i["sku"] == "SKU-DT-1KG")
    corrected = ok(as_user("order_desk", "PATCH", f"/orders/{order_id}/items/{detergent['id']}",
                           json={"new_quantity": 5, "reason": "Retailer phoned"}))
    line = next(i for i in corrected["items"] if i["sku"] == "SKU-DT-1KG")
    assert Decimal(line["discount_percentage"]) == 3 and line["scheme"]["description"] == "3% off on 5+"
    assert [(Decimal(c["old_quantity"]), Decimal(c["new_quantity"]), c["reason"]) for c in line["corrections"]] == [
        (4, 5, "Retailer phoned")]

    # Hold needs a reason; a held order stays held after a correction.
    assert as_user("order_desk", "POST", f"/orders/{order_id}/hold", json={"reason": ""}).status_code == 422
    held = ok(as_user("order_desk", "POST", f"/orders/{order_id}/hold", json={"reason": "Confirm delivery date"}))
    assert (held["status"], held["hold_reason"]) == ("ON_HOLD", "Confirm delivery date")
    biscuit = next(i for i in held["items"] if i["sku"] == "SKU-BS-075")
    held = ok(as_user("order_desk", "PATCH", f"/orders/{order_id}/items/{biscuit['id']}", json={"new_quantity": 11, "reason": "Retailer phoned"}))
    assert held["status"] == "ON_HOLD"

    # Confirm: stock (paid + free) is deducted.
    stock_before = tx.scalar(select(Inventory.stock_cases).where(Inventory.product_id == BS075))
    confirmed = ok(as_user("order_desk", "POST", f"/orders/{order_id}/approve", json={}))
    assert confirmed["status"] == "APPROVED" and confirmed["approved_at"]
    tx.expire_all()
    assert tx.scalar(select(Inventory.stock_cases).where(Inventory.product_id == BS075)) == stock_before - 12
    assert err(as_user("order_desk", "POST", f"/orders/{order_id}/hold", json={"reason": "late"})) == (
        409, "INVALID_ORDER_STATUS")

    # The retailer sees the confirmed order.
    assert ok(as_user("retailer_sharma", "GET", f"/orders/{order_id}"))["status"] == "APPROVED"

    # Tally export: one row per line of confirmed orders, values from the snapshots.
    response = as_user("order_desk", "GET", "/exports/tally/orders.csv")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    mine = [r for r in rows if r["Voucher Number"] == placed["order_number"]]
    by_sku = {r["SKU"]: r for r in mine}
    assert set(by_sku) == {"SKU-BS-075", "SKU-DT-1KG"}
    assert by_sku["SKU-BS-075"]["Billed Qty"] == "11" and by_sku["SKU-BS-075"]["Free Qty"] == "1"
    assert by_sku["SKU-BS-075"]["Rate"] == "8.10" and by_sku["SKU-BS-075"]["Rate Per"] == "piece"
    assert by_sku["SKU-BS-075"]["Rate Includes GST"] == "No"
    assert by_sku["SKU-DT-1KG"]["Discount %"] == "3.00" and by_sku["SKU-DT-1KG"]["Scheme"] == "3% off on 5+"
    assert by_sku["SKU-DT-1KG"]["Party GSTIN"] == "23AAAPS1234A1Z5"
    assert sum(Decimal(r["Line Amount"]) for r in mine) == Decimal(confirmed["grand_total"])
    # Only confirmed orders are exported.
    assert all(r["Voucher Number"] != "DF-DEMO-0002" for r in rows)  # PENDING demo order


def test_export_date_filter(as_user):
    assert as_user("order_desk", "GET", "/exports/tally/orders.csv",
                   params={"from_date": "2026-12-01", "to_date": "2026-11-01"}).status_code == 422
    future = as_user("order_desk", "GET", "/exports/tally/orders.csv", params={"from_date": "2999-01-01"})
    assert future.content.decode("utf-8-sig").strip().count("\n") == 0  # header only


def test_one_click_reject_and_rejected_order_cannot_be_confirmed(as_user, tx):
    order = {"id": str(place_open_order(tx, "retailer_sharma", (BS075, 1)).id)}
    # One click: no body needed; a default reason is stored and shown to the retailer.
    rejected = ok(as_user("order_desk", "POST", f"/orders/{order['id']}/reject"))
    assert (rejected["status"], rejected["rejection_reason"]) == ("REJECTED", "Rejected by the order desk")
    assert err(as_user("order_desk", "POST", f"/orders/{order['id']}/approve", json={})) == (409, "INVALID_ORDER_STATUS")


def test_desk_queue_has_catalogue_salesman_and_ai_orders(as_user, tx):
    manual = ok(as_user("retailer_sharma", "POST", "/orders", json=cart((BS075, 1))), 201)
    salesman = ok(as_user("salesman_sunil", "POST", "/orders", json=cart((BS075, 1), retailer_id=str(SHARMA))), 201)
    ai = place_open_order(tx, "retailer_sharma", (BS075, 2))
    queue = ok(as_user("order_desk", "GET", "/orders",
                       params={"status": ["PENDING", "CREDIT_HOLD", "ON_HOLD"], "limit": 100}))["items"]
    ids = {o["id"] for o in queue}
    assert {str(ai.id), manual["id"], salesman["id"]} <= ids
    # The desk can reject a catalogue order: nothing was deducted, the credit hold is released.
    rejected = ok(as_user("order_desk", "POST", f"/orders/{manual['id']}/reject", json={"reason": "Out of route"}))
    assert rejected["status"] == "REJECTED" and rejected["rejection_reason"] == "Out of route"
