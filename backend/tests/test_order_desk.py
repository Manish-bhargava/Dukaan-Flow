"""Order Desk: sections, review data, validation warnings, clarification, history, Tally
export marking and dispatch lists, through the HTTP API."""

import csv
import io
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from app.models import CreditAccount, Inventory, Order, RetailerPrice
from seed.run_seed import seed_id
from tests.conftest import place_open_order
from tests.test_orders_api import accepted, as_user, cart, err, ok  # noqa: F401  (as_user is a fixture)

BS075, DT1KG = (seed_id("product", s) for s in ("SKU-BS-075", "SKU-DT-1KG"))
SHARMA = seed_id("retailer", "sharma")
SUNIL = seed_id("user", "salesman_sunil")


def desk(as_user, url, **params):
    return ok(as_user("order_desk", "GET", url, params=params))


def actions(review):
    return [e["action"] for e in review["history"]]


@pytest.fixture
def roomy_credit(tx):
    tx.execute(update(CreditAccount).where(CreditAccount.retailer_id == SHARMA).values(credit_limit=Decimal("500000")))
    tx.commit()


# ---------------------------------------------------------------- access


@pytest.mark.parametrize("user", ["retailer_sharma", "salesman_sunil"])
@pytest.mark.parametrize("method,url,body", [
    ("GET", "/order-desk/overview", None),
    ("GET", "/order-desk/orders", None),
    ("GET", "/order-desk/dispatch", None),
    ("GET", "/order-desk/salesmen", None),
    ("POST", "/exports/tally", {}),
])
def test_order_desk_endpoints_are_desk_only(as_user, user, method, url, body):
    assert err(as_user(user, method, url, json=body)) == (403, "FORBIDDEN")


def test_review_and_clarification_are_desk_only(as_user, tx):
    order_id = place_open_order(tx, "retailer_sharma", (BS075, 1)).id
    assert err(as_user("retailer_sharma", "GET", f"/order-desk/orders/{order_id}")) == (403, "FORBIDDEN")
    assert err(as_user("salesman_sunil", "POST", f"/orders/{order_id}/clarification",
                       json={"message": "which pack?"})) == (403, "FORBIDDEN")


# ---------------------------------------------------------------- sections


def test_incoming_lists_open_orders_with_salesman_search_filters_and_sorting(as_user, tx, roomy_credit):
    small = place_open_order(tx, "retailer_sharma", (BS075, 1))
    big = place_open_order(tx, "retailer_sharma", (BS075, 20))
    catalogue = ok(as_user("retailer_sharma", "POST", "/orders", json=cart((DT1KG, 1))), 201)
    confirmed = accepted(as_user, "retailer_sharma", cart((DT1KG, 1)))

    rows = desk(as_user, "/order-desk/orders", view="incoming", limit=50)["items"]
    ids = [r["id"] for r in rows]
    # Catalogue orders arrive here too; accepted ones move to Confirmed.
    assert {str(small.id), str(big.id), catalogue["id"]} <= set(ids) and confirmed["id"] not in ids
    row = next(r for r in rows if r["id"] == str(big.id))
    assert row["salesman"]["name"] == "Sunil Yadav"  # Sharma's assigned salesman
    assert row["retailer"]["phone"] and row["last_action"]["action"] == "RECEIVED"

    by_phone = desk(as_user, "/order-desk/orders", view="incoming", search=row["retailer"]["phone"], limit=50)
    assert str(big.id) in {r["id"] for r in by_phone["items"]}
    by_salesman = desk(as_user, "/order-desk/orders", view="incoming", salesman_id=str(SUNIL), limit=50)
    assert str(big.id) in {r["id"] for r in by_salesman["items"]}
    other = desk(as_user, "/order-desk/orders", view="incoming", salesman_id=str(seed_id("user", "salesman_deepak")), limit=50)
    assert str(big.id) not in {r["id"] for r in other["items"]}

    by_value = desk(as_user, "/order-desk/orders", view="incoming", sort="value_desc", limit=50)["items"]
    totals = [Decimal(r["grand_total"]) for r in by_value]
    assert totals == sorted(totals, reverse=True)

    confirmed_rows = desk(as_user, "/order-desk/orders", view="confirmed", limit=50)["items"]
    assert confirmed["id"] in {r["id"] for r in confirmed_rows}
    assert err(as_user("order_desk", "GET", "/order-desk/orders", params={"view": "nope"})) == (422, "VALIDATION_ERROR")


def test_review_shows_retailer_credit_stock_and_history(as_user, tx):
    order = place_open_order(tx, "retailer_sharma", (BS075, 2))
    review = desk(as_user, f"/order-desk/orders/{order.id}")
    assert review["order"]["retailer"]["owner_name"] and review["salesman"]["name"] == "Sunil Yadav"
    credit = review["credit"]
    assert Decimal(credit["available_credit"]) == (Decimal(credit["credit_limit"]) - Decimal(credit["current_outstanding"])
                                                   - Decimal(credit["reserved_for_review"]))
    [line] = review["stock"]
    assert line["ok"] and Decimal(line["needed"]) == 2
    assert actions(review) == ["RECEIVED"] and review["history"][0]["actor"]["name"]
    assert review["warnings"] == []


# ---------------------------------------------------------------- warnings


def test_stock_and_credit_problems_are_warnings(as_user, tx):
    order = place_open_order(tx, "retailer_sharma", (BS075, 2))
    tx.execute(update(Inventory).where(Inventory.product_id == BS075).values(stock_cases=1))
    tx.execute(update(CreditAccount).where(CreditAccount.retailer_id == SHARMA).values(credit_limit=Decimal("0")))
    tx.commit()
    codes = {w["code"]: w for w in desk(as_user, f"/order-desk/orders/{order.id}")["warnings"]}
    assert codes["INSUFFICIENT_STOCK"]["severity"] == "error" and "1 in stock" in codes["INSUFFICIENT_STOCK"]["message"]
    assert codes["CREDIT_LIMIT_EXCEEDED"]["severity"] == "error"
    overview = desk(as_user, "/order-desk/overview")
    assert overview["with_stock_or_credit_issues"] >= 1
    assert err(as_user("order_desk", "POST", f"/orders/{order.id}/approve", json={})) == (409, "INSUFFICIENT_STOCK")


def test_price_change_since_placement_is_flagged_and_never_applied_silently(as_user, tx, roomy_credit):
    order = place_open_order(tx, "retailer_sharma", (BS075, 2))
    placed_price = order.items[0].unit_price
    tx.execute(update(RetailerPrice).where(RetailerPrice.retailer_id == SHARMA, RetailerPrice.product_id == BS075,
                                           RetailerPrice.effective_to.is_(None)).values(dealer_price=placed_price + 1))
    tx.commit()

    warnings = desk(as_user, f"/order-desk/orders/{order.id}")["warnings"]
    assert [w["code"] for w in warnings] == ["PRICE_CHANGED"]
    status, code = err(as_user("order_desk", "POST", f"/orders/{order.id}/approve", json={}))
    assert (status, code) == (409, "ORDER_DATA_CHANGED")
    confirmed = ok(as_user("order_desk", "POST", f"/orders/{order.id}/approve", json={"acknowledge_changes": True}))
    assert confirmed["status"] == "APPROVED" and Decimal(confirmed["items"][0]["unit_price"]) == placed_price


def test_identical_orders_close_together_are_possible_duplicates(as_user, tx, roomy_credit):
    first = place_open_order(tx, "retailer_sharma", (BS075, 3))
    second = place_open_order(tx, "retailer_sharma", (BS075, 3))
    warnings = desk(as_user, f"/order-desk/orders/{second.id}")["warnings"]
    assert [w["code"] for w in warnings] == ["POSSIBLE_DUPLICATE"] and first.order_number in warnings[0]["message"]
    different = place_open_order(tx, "retailer_sharma", (BS075, 4))
    assert desk(as_user, f"/order-desk/orders/{different.id}")["warnings"] == []


def test_offline_order_with_changed_price_is_held_with_its_original_lines(as_user, tx, roomy_credit):
    body = cart((BS075, 2), retailer_id=str(SHARMA), created_offline=True, client_order_id="desk-test-offline-1")
    body["items"][0]["expected_unit_price"] = "1.00"
    placed = ok(as_user("salesman_sunil", "POST", "/orders", json=body), 201)
    assert placed["status"] == "ON_HOLD"

    row = next(r for r in desk(as_user, "/order-desk/orders", view="incoming", source="SALESMAN", limit=50)["items"]
               if r["id"] == placed["id"])
    assert row["created_offline"] and row["salesman"]["name"] == "Sunil Yadav"
    assert [w["code"] for w in row["warnings"]] == ["OFFLINE_DATA_CHANGED"]
    assert "price changed" in row["warnings"][0]["message"]

    confirmed = ok(as_user("order_desk", "POST", f"/orders/{placed['id']}/approve", json={}))
    assert confirmed["status"] == "APPROVED" and Decimal(confirmed["items"][0]["paid_quantity"]) == 2


# ---------------------------------------------------------------- actions and history


def test_clarification_keeps_order_and_credit_then_desk_corrects_and_confirms(as_user, tx, roomy_credit):
    order = place_open_order(tx, "retailer_sharma", (BS075, 2), (DT1KG, 1))
    before = ok(as_user("retailer_sharma", "GET", "/retailers/me"))["credit"]["available_credit"]

    assert as_user("order_desk", "POST", f"/orders/{order.id}/clarification", json={"message": " "}).status_code == 422
    asked = ok(as_user("order_desk", "POST", f"/orders/{order.id}/clarification",
                       json={"message": "Biscuits: 75g or 150g pack?"}))
    assert (asked["status"], asked["clarification_message"]) == ("CLARIFICATION_REQUIRED", "Biscuits: 75g or 150g pack?")
    assert [Decimal(i["paid_quantity"]) for i in asked["items"]] == [2, 1]  # unchanged

    # It moves from Incoming to Clarification Required, keeps holding credit, and the
    # retailer can see the question.
    assert str(order.id) not in {r["id"] for r in desk(as_user, "/order-desk/orders", view="incoming", limit=50)["items"]}
    row = next(r for r in desk(as_user, "/order-desk/orders", view="clarification", limit=50)["items"]
               if r["id"] == str(order.id))
    assert row["reason"] == "Biscuits: 75g or 150g pack?" and row["last_action"]["action"] == "CLARIFICATION_REQUESTED"
    assert ok(as_user("retailer_sharma", "GET", "/retailers/me"))["credit"]["available_credit"] == before
    mine = ok(as_user("retailer_sharma", "GET", f"/orders/{order.id}"))
    assert mine["clarification_message"] == "Biscuits: 75g or 150g pack?"

    # The desk corrects a line (stays in clarification), then confirms.
    biscuit = next(i for i in asked["items"] if i["sku"] == "SKU-BS-075")
    corrected = ok(as_user("order_desk", "PATCH", f"/orders/{order.id}/items/{biscuit['id']}",
                           json={"new_quantity": 3, "reason": "Retailer confirmed 3 cases"}))
    assert corrected["status"] == "CLARIFICATION_REQUIRED"
    confirmed = ok(as_user("order_desk", "POST", f"/orders/{order.id}/approve", json={}))
    assert confirmed["status"] == "APPROVED" and confirmed["approved_by"]["name"]

    review = desk(as_user, f"/order-desk/orders/{order.id}")
    assert actions(review) == ["RECEIVED", "CLARIFICATION_REQUESTED", "CORRECTED", "CONFIRMED"]
    correction = review["history"][2]
    assert correction["message"] == "Retailer confirmed 3 cases"
    assert (correction["details"]["old"]["quantity"], correction["details"]["new"]["quantity"]) == ("2.000", "3")
    assert all(e["actor"] for e in review["history"])
    assert err(as_user("order_desk", "POST", f"/orders/{order.id}/approve", json={})) == (409, "INVALID_ORDER_STATUS")
    assert err(as_user("order_desk", "POST", f"/orders/{order.id}/clarification",
                       json={"message": "?"})) == (409, "INVALID_ORDER_STATUS")


def test_correction_needs_a_reason(as_user, tx):
    order = place_open_order(tx, "retailer_sharma", (BS075, 2))
    item_id = order.items[0].id
    for body in ({"new_quantity": 3}, {"new_quantity": 3, "reason": "  "}):
        assert as_user("order_desk", "PATCH", f"/orders/{order.id}/items/{item_id}", json=body).status_code == 422
    assert actions(desk(as_user, f"/order-desk/orders/{order.id}")) == ["RECEIVED"]


def test_rejection_is_recorded_and_listed(as_user, tx):
    order = place_open_order(tx, "retailer_sharma", (BS075, 1))
    ok(as_user("order_desk", "POST", f"/orders/{order.id}/reject", json={"reason": "Shop closed for renovation"}))
    row = next(r for r in desk(as_user, "/order-desk/orders", view="rejected", limit=50)["items"] if r["id"] == str(order.id))
    assert row["reason"] == "Shop closed for renovation"
    assert row["last_action"]["action"] == "REJECTED" and row["last_action"]["actor"]["role"] == "ORDER_DESK"
    assert ok(as_user("retailer_sharma", "GET", f"/orders/{order.id}"))["rejection_reason"] == "Shop closed for renovation"
    assert desk(as_user, "/order-desk/overview")["rejected_today"] >= 1


# ---------------------------------------------------------------- Tally export and dispatch


def test_tally_export_marks_orders_and_never_repeats_by_accident(as_user, tx, roomy_credit):
    # Only this test's orders: everything confirmed before is marked exported first.
    tx.execute(update(Order).where(Order.status == "APPROVED").values(tally_exported_at=Order.approved_at))
    tx.commit()
    placed = accepted(as_user, "retailer_sharma", cart((BS075, 2), (DT1KG, 1)))
    assert desk(as_user, "/order-desk/overview")["not_exported"] == 1

    response = as_user("order_desk", "POST", "/exports/tally", json={})
    assert response.status_code == 200 and response.headers["x-exported-count"] == "1"
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert {r["Voucher Number"] for r in rows} == {placed["order_number"]} and len(rows) == 2

    assert err(as_user("order_desk", "POST", "/exports/tally", json={})) == (409, "NOTHING_TO_EXPORT")
    review = desk(as_user, f"/order-desk/orders/{placed['id']}")
    assert review["order"]["tally_exported_at"] and actions(review)[-1] == "EXPORTED"
    exported = desk(as_user, "/order-desk/orders", view="confirmed", exported="true", limit=50)["items"]
    assert placed["id"] in {r["id"] for r in exported}
    assert placed["id"] not in {r["id"] for r in desk(as_user, "/order-desk/orders", view="confirmed", exported="false", limit=50)["items"]}

    again = as_user("order_desk", "POST", "/exports/tally", json={"order_ids": [placed["id"]], "include_exported": True})
    assert again.status_code == 200 and again.headers["x-exported-count"] == "1"
    history = desk(as_user, f"/order-desk/orders/{placed['id']}")["history"]
    assert [e["details"]["re_export"] for e in history if e["action"] == "EXPORTED"] == [False, True]


def test_dispatch_consolidates_confirmed_quantities_by_salesman_beat(as_user, tx, roomy_credit):
    a = accepted(as_user, "retailer_sharma", cart((BS075, 25)))  # 25 + 2 free
    b = accepted(as_user, "salesman_sunil", cart((BS075, 1), (DT1KG, 2), retailer_id=str(SHARMA)))
    data = desk(as_user, "/order-desk/dispatch")
    mine = {a["id"], b["id"]}
    beat = next(beat for beat in data["beats"] if beat["salesman"] and beat["salesman"]["name"] == "Sunil Yadav")
    [sharma] = [s for s in beat["stops"] if s["shop_name"] == "Sharma Kirana Store"]  # one stop per shop
    assert mine <= {o["order_id"] for o in sharma["orders"]}
    assert Decimal(sharma["grand_total"]) == sum(Decimal(o["grand_total"]) for o in sharma["orders"])
    biscuits = next(p for p in data["products"] if p["sku"] == "SKU-BS-075")
    expected = sum(Decimal(i["paid_quantity"]) + Decimal(i["free_quantity"])
                   for o in (a, b) for i in o["items"] if i["sku"] == "SKU-BS-075")
    assert Decimal(biscuits["total"]) >= expected and Decimal(biscuits["free"]) >= 2
    assert Decimal(data["grand_total"]) == sum(Decimal(beat["grand_total"]) for beat in data["beats"])
    future = desk(as_user, "/order-desk/dispatch", from_date="2999-01-01", to_date="2999-01-01")
    assert future["order_count"] == 0 and future["products"] == []
