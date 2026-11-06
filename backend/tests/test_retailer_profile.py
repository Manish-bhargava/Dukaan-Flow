"""Retailer profile (GET /retailers/me), the retailer credit restriction on placing orders,
and order/AI-draft status visibility for the retailer."""

import json
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select, update

from app.core.config import settings
from app.core.security import create_access_token
from app.models import CreditAccount, Order
from app.modules.ai_orders import llm
from seed.run_seed import seed_id
from tests.conftest import place_open_order, seed_user

BS075, DT1KG = seed_id("product", "SKU-BS-075"), seed_id("product", "SKU-DT-1KG")
SHARMA = seed_id("retailer", "sharma")


@pytest.fixture
def as_user(tx_client, tx):
    def call(key, method, url, **kw):
        token, _ = create_access_token(seed_user(tx, key))
        return tx_client.request(method, f"/api/v1{url}", headers={"Authorization": f"Bearer {token}"}, **kw)
    return call


def cart(*lines):
    return {"items": [{"product_id": str(p), "quantity": q, "unit": "case"} for p, q in lines]}


def data(response, status=200):
    assert response.status_code == status, response.json()
    return response.json()["data"]


def set_credit(tx, limit=None, outstanding=None):
    values = {k: v for k, v in (("credit_limit", limit), ("current_outstanding", outstanding)) if v is not None}
    tx.execute(update(CreditAccount).where(CreditAccount.retailer_id == SHARMA).values(**values))
    tx.commit()  # releases the savepoint only; the test transaction is still rolled back at the end


# ---------------------------------------------------------------- profile


def test_profile_shows_real_retailer_details_and_credit(as_user):
    p = data(as_user("retailer_sharma", "GET", "/retailers/me"))
    assert (p["id"], p["shop_name"], p["owner_name"], p["phone"]) == (
        str(SHARMA), "Sharma Kirana Store", "Ramesh Sharma", "9000000101")
    assert p["address"] == "12, Napier Town Main Road" and p["city"] == "Jabalpur"
    assert p["assigned_salesman"] == {"name": "Sunil Yadav", "phone": "9000000003"}
    assert p["credit"] == {"credit_limit": "50000.00", "current_outstanding": "35000.00",
                           "reserved_for_review": "0", "available_credit": "15000.00"}
    assert p["can_place_orders"] is True


def test_purchase_summary_counts_only_confirmed_orders_as_purchased(as_user, tx):
    confirmed = data(as_user("retailer_sharma", "POST", "/orders", json=cart((BS075, 1))), 201)
    data(as_user("order_desk", "POST", f"/orders/{confirmed['id']}/approve", json={}))  # accepted by the desk
    pending = {"grand_total": str(place_open_order(tx, "retailer_sharma", (BS075, 2)).grand_total)}
    rejected = place_open_order(tx, "retailer_sharma", (BS075, 3))
    data(as_user("order_desk", "POST", f"/orders/{rejected.id}/reject", json={"reason": "Duplicate"}))

    p = data(as_user("retailer_sharma", "GET", "/retailers/me"))
    s = p["purchases"]
    assert Decimal(s["total_purchased"]) == Decimal(confirmed["grand_total"])  # rejected/pending excluded
    assert (s["total_orders"], s["confirmed_orders"], s["under_review_orders"], s["rejected_orders"]) == (3, 1, 1, 1)
    assert Decimal(s["under_review_amount"]) == Decimal(pending["grand_total"])
    # Confirming debited credit: outstanding went up by the confirmed order's total.
    assert Decimal(p["credit"]["current_outstanding"]) == Decimal("35000.00") + Decimal(confirmed["grand_total"])
    assert Decimal(p["credit"]["reserved_for_review"]) == Decimal(pending["grand_total"])
    assert Decimal(p["credit"]["available_credit"]) == (
        Decimal("15000.00") - Decimal(confirmed["grand_total"]) - Decimal(pending["grand_total"]))


@pytest.mark.parametrize("key", ["order_desk", "admin", "salesman_sunil"])
def test_profile_is_retailer_only(as_user, key):
    assert as_user(key, "GET", "/retailers/me").status_code == 403


def test_profile_requires_login(tx_client):
    assert tx_client.get("/api/v1/retailers/me").status_code == 401


# ---------------------------------------------------------------- credit restriction


def test_quote_reports_whether_cart_fits_available_credit(as_user):
    fits = data(as_user("retailer_sharma", "POST", "/orders/quote", json=cart((BS075, 10))))  # 8,164.80
    too_big = data(as_user("retailer_sharma", "POST", "/orders/quote", json=cart((BS075, 25))))  # 20,412.00
    assert (fits["within_credit"], fits["available_credit"]) == (True, "15000.00")
    assert too_big["within_credit"] is False


def test_order_exactly_at_available_credit_is_allowed(as_user, tx):
    total = Decimal(data(as_user("retailer_sharma", "POST", "/orders/quote", json=cart((BS075, 10))))["totals"]["grand_total"])
    set_credit(tx, limit=Decimal("35000.00") + total)  # available == order total
    assert data(as_user("retailer_sharma", "POST", "/orders", json=cart((BS075, 10))), 201)["status"] == "PENDING"


def test_retailer_cannot_bypass_credit_by_calling_the_api(as_user, tx):
    before = tx.scalar(select(func.count()).select_from(Order))
    response = as_user("retailer_sharma", "POST", "/orders", json=cart((BS075, 25)))
    assert (response.status_code, response.json()["error_code"]) == (409, "CREDIT_LIMIT_EXCEEDED")
    assert "salesman" in response.json()["message"] and "order desk" in response.json()["message"]
    assert tx.scalar(select(func.count()).select_from(Order)) == before


def test_credit_limit_reached_blocks_every_order_but_not_browsing(as_user, tx):
    set_credit(tx, outstanding=Decimal("50000.00"))  # available = 0
    p = data(as_user("retailer_sharma", "GET", "/retailers/me"))
    assert (p["credit"]["available_credit"], p["can_place_orders"]) == ("0.00", False)
    response = as_user("retailer_sharma", "POST", "/orders", json=cart((BS075, 1)))
    assert response.json()["error_code"] == "CREDIT_LIMIT_EXCEEDED"
    assert response.json()["message"].startswith("Your credit limit has been reached.")
    # Browsing, offers, quotes and old orders still work.
    assert as_user("retailer_sharma", "GET", "/products").status_code == 200
    assert as_user("retailer_sharma", "GET", "/products", params={"has_scheme": "true"}).status_code == 200
    assert data(as_user("retailer_sharma", "POST", "/orders/quote", json=cart((BS075, 1))))["within_credit"] is False
    assert as_user("retailer_sharma", "GET", "/orders").status_code == 200


def test_salesman_over_credit_order_still_goes_to_credit_hold(as_user):
    payload = {**cart((BS075, 25)), "retailer_id": str(SHARMA)}
    assert data(as_user("salesman_sunil", "POST", "/orders", json=payload), 201)["status"] == "CREDIT_HOLD"


# ---------------------------------------------------------------- AI order status visibility


@pytest.fixture
def openai(monkeypatch):
    lines = [{"original_text": "12 peti biscuit chhota", "product_description": "glucose biscuit 75g", "quantity": 12,
              "unit": "case", "candidate_skus": ["SKU-BS-075"], "confidence": 0.95},
             {"original_text": "kuch sabun", "product_description": "soap", "quantity": None, "unit": None,
              "candidate_skus": [], "confidence": 0.0}]

    def handler(request):
        content = json.dumps({"lines": lines})
        return httpx.Response(200, json={"model": "gpt-test", "choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(llm, "_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))


def test_ai_order_moves_from_draft_to_under_review_to_confirmed(as_user, openai):
    draft = data(as_user("retailer_sharma", "POST", "/ai-orders/extract", json={"message": "12 peti biscuit chhota, kuch sabun"}))

    # Draft: listed as a draft needing clarification, not as an order.
    [summary] = data(as_user("retailer_sharma", "GET", "/ai-orders"))
    assert summary["extraction_id"] == draft["extraction_id"] and summary["needs_clarification"] is True
    assert summary["item_count"] == 2
    my_orders = data(as_user("retailer_sharma", "GET", "/orders", params={"source": "AI"}))["items"]
    assert my_orders == []

    # Placed: it becomes an order under review (PENDING) and leaves the draft list.
    biscuit = draft["items"][0]
    body = {"items": [{"extraction_item_id": biscuit["id"], "product_id": str(BS075), "quantity": 12, "unit": "case"}]}
    order = data(as_user("retailer_sharma", "POST", f"/ai-orders/{draft['extraction_id']}/confirm", json=body), 201)
    assert (order["source"], order["status"]) == ("AI", "PENDING")
    assert data(as_user("retailer_sharma", "GET", "/ai-orders")) == []
    [listed] = data(as_user("retailer_sharma", "GET", "/orders", params={"source": "AI"}))["items"]
    assert (listed["id"], listed["status"]) == (order["id"], "PENDING")

    # Order Desk accepts it: the retailer sees it confirmed.
    data(as_user("order_desk", "POST", f"/orders/{order['id']}/approve", json={}))
    assert data(as_user("retailer_sharma", "GET", f"/orders/{order['id']}"))["status"] == "APPROVED"
    [listed] = data(as_user("retailer_sharma", "GET", "/orders", params={"source": "AI"}))["items"]
    assert listed["status"] == "APPROVED"


def test_rejected_ai_order_shows_rejected_with_reason(as_user, openai):
    draft = data(as_user("retailer_sharma", "POST", "/ai-orders/extract", json={"message": "12 peti biscuit chhota"}))
    body = {"items": [{"extraction_item_id": draft["items"][0]["id"], "product_id": str(BS075), "quantity": 2, "unit": "case"}]}
    order = data(as_user("retailer_sharma", "POST", f"/ai-orders/{draft['extraction_id']}/confirm", json=body), 201)
    data(as_user("order_desk", "POST", f"/orders/{order['id']}/reject", json={"reason": "Wrong product"}))
    seen = data(as_user("retailer_sharma", "GET", f"/orders/{order['id']}"))
    assert (seen["status"], seen["rejection_reason"]) == ("REJECTED", "Wrong product")


def test_ai_draft_over_credit_cannot_be_placed(as_user, openai):
    draft = data(as_user("retailer_sharma", "POST", "/ai-orders/extract", json={"message": "25 peti biscuit chhota"}))
    body = {"items": [{"extraction_item_id": draft["items"][0]["id"], "product_id": str(BS075), "quantity": 25, "unit": "case"}]}
    response = as_user("retailer_sharma", "POST", f"/ai-orders/{draft['extraction_id']}/confirm", json=body)
    assert (response.status_code, response.json()["error_code"]) == (409, "CREDIT_LIMIT_EXCEEDED")
    assert len(data(as_user("retailer_sharma", "GET", "/ai-orders"))) == 1  # still a draft


def test_drafts_are_private_to_the_retailer(as_user, openai):
    data(as_user("retailer_sharma", "POST", "/ai-orders/extract", json={"message": "12 peti biscuit chhota"}))
    assert data(as_user("retailer_gupta", "GET", "/ai-orders")) == []
    assert as_user("order_desk", "GET", "/ai-orders").status_code == 403


# ---------------------------------------------------------------- credit in real time


def credit_now(as_user):
    c = data(as_user("retailer_sharma", "GET", "/retailers/me"))["credit"]
    return {k: Decimal(v) for k, v in c.items()}


def test_catalogue_order_holds_credit_until_the_desk_accepts(as_user):
    before = credit_now(as_user)
    order = data(as_user("retailer_sharma", "POST", "/orders", json=cart((BS075, 5))), 201)
    held = credit_now(as_user)
    total = Decimal(order["grand_total"])
    assert order["status"] == "PENDING"
    assert held["reserved_for_review"] == before["reserved_for_review"] + total
    assert held["available_credit"] == before["available_credit"] - total
    assert held["current_outstanding"] == before["current_outstanding"]
    data(as_user("order_desk", "POST", f"/orders/{order['id']}/approve", json={}))
    after = credit_now(as_user)
    assert after["current_outstanding"] == before["current_outstanding"] + total
    assert after["available_credit"] == before["available_credit"] - total
    assert after["reserved_for_review"] == before["reserved_for_review"]


def test_ai_order_holds_credit_until_rejected(as_user, openai):
    before = credit_now(as_user)
    draft = data(as_user("retailer_sharma", "POST", "/ai-orders/extract", json={"message": "12 peti biscuit chhota"}))
    assert credit_now(as_user) == before  # a draft is not an order: no credit used
    body = {"items": [{"extraction_item_id": draft["items"][0]["id"], "product_id": str(BS075), "quantity": 12, "unit": "case"}]}
    order = data(as_user("retailer_sharma", "POST", f"/ai-orders/{draft['extraction_id']}/confirm", json=body), 201)
    total = Decimal(order["grand_total"])

    held = credit_now(as_user)  # under review: held, not yet outstanding
    assert held["reserved_for_review"] == total and held["current_outstanding"] == before["current_outstanding"]
    assert held["available_credit"] == before["available_credit"] - total

    data(as_user("order_desk", "POST", f"/orders/{order['id']}/reject", json={"reason": "Not needed"}))
    assert credit_now(as_user) == before  # rejected: credit comes back


def test_ai_order_moves_credit_to_outstanding_when_accepted(as_user, openai):
    before = credit_now(as_user)
    draft = data(as_user("retailer_sharma", "POST", "/ai-orders/extract", json={"message": "12 peti biscuit chhota"}))
    body = {"items": [{"extraction_item_id": draft["items"][0]["id"], "product_id": str(BS075), "quantity": 12, "unit": "case"}]}
    order = data(as_user("retailer_sharma", "POST", f"/ai-orders/{draft['extraction_id']}/confirm", json=body), 201)
    data(as_user("order_desk", "POST", f"/orders/{order['id']}/approve", json={}))
    after = credit_now(as_user)
    total = Decimal(order["grand_total"])
    assert after["reserved_for_review"] == 0
    assert after["current_outstanding"] == before["current_outstanding"] + total
    assert after["available_credit"] == before["available_credit"] - total
