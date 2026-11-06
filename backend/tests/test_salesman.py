"""Salesman module: assigned retailers only, offline sync bundle, salesman orders through
the common order system (attribution, idempotent sync, offline review rules), visits."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, update

from app.core.security import create_access_token
from app.models import Inventory, Order, RetailerPrice, ShopVisit
from seed.run_seed import seed_id
from tests.conftest import seed_user

SHARMA, GUPTA, JAIN, PATEL = (seed_id("retailer", k) for k in ("sharma", "gupta", "jain", "patel"))
BS075, DT1KG, TE250 = (seed_id("product", s) for s in ("SKU-BS-075", "SKU-DT-1KG", "SKU-TE-250"))
SUNIL = seed_id("user", "salesman_sunil")


@pytest.fixture
def as_user(tx_client, tx):
    def call(key, method, url, **kw):
        token, _ = create_access_token(seed_user(tx, key))
        return tx_client.request(method, f"/api/v1{url}", headers={"Authorization": f"Bearer {token}"}, **kw)
    return call


def data(response, status=200):
    assert response.status_code == status, response.json()
    return response.json()["data"]


def order_body(retailer_id, *lines, **extra):
    return {"retailer_id": str(retailer_id),
            "items": [{"product_id": str(p), "quantity": q, "unit": "case", **({"expected_unit_price": e} if e else {})}
                      for p, q, *rest in lines for e in [rest[0] if rest else None]],
            **extra}


def client_id():
    return uuid.uuid4().hex


# ---------------------------------------------------------------- assigned retailers / bundle


def test_bundle_has_only_assigned_active_retailers(as_user):
    bundle = data(as_user("salesman_sunil", "GET", "/salesman/sync-bundle"))
    ids = {r["id"] for r in bundle["retailers"]}
    assert ids == {str(SHARMA), str(GUPTA), str(JAIN)}  # Patel is Deepak's, Agrawal is unassigned
    deepak = data(as_user("salesman_deepak", "GET", "/salesman/sync-bundle"))
    assert {r["id"] for r in deepak["retailers"]} == {str(PATEL)}
    assert set(bundle["prices"]) == ids


def test_inactive_assigned_retailer_is_left_out(as_user, tx):
    from app.models import Retailer
    tx.execute(update(Retailer).where(Retailer.id == JAIN).values(is_active=False))
    tx.commit()
    bundle = data(as_user("salesman_sunil", "GET", "/salesman/sync-bundle"))
    assert str(JAIN) not in {r["id"] for r in bundle["retailers"]}


def test_bundle_has_retailer_details_credit_prices_stock_and_schemes(as_user):
    bundle = data(as_user("salesman_sunil", "GET", "/salesman/sync-bundle"))
    sharma = next(r for r in bundle["retailers"] if r["id"] == str(SHARMA))
    assert (sharma["shop_name"], sharma["owner_name"], sharma["phone"]) == ("Sharma Kirana Store", "Ramesh Sharma", "9000000101")
    assert sharma["credit"]["available_credit"] == "15000.00"
    biscuit = next(p for p in bundle["products"] if p["sku"] == "SKU-BS-075")
    assert biscuit["stock_cases"] == "340.000" and biscuit["schemes"][0]["description"] == "Buy 10 get 1 free"
    assert bundle["prices"][str(SHARMA)][str(BS075)]["case_price"] == "777.60"
    # Each retailer's own price
    assert bundle["prices"][str(SHARMA)][str(BS075)] != bundle["prices"][str(GUPTA)][str(BS075)]
    assert datetime.fromisoformat(bundle["synced_at"]) <= datetime.now(UTC)


@pytest.mark.parametrize("key", ["retailer_sharma", "order_desk", "admin"])
def test_bundle_is_salesman_only(as_user, key):
    assert as_user(key, "GET", "/salesman/sync-bundle").status_code == 403


def test_unassigned_retailer_is_blocked_everywhere(as_user, tx):
    patel = str(PATEL)
    assert as_user("salesman_sunil", "GET", "/products", params={"retailer_id": patel}).status_code == 403
    assert as_user("salesman_sunil", "POST", "/orders/quote", json=order_body(PATEL, (BS075, 1))).status_code == 403
    assert as_user("salesman_sunil", "POST", "/orders", json=order_body(PATEL, (BS075, 1))).status_code == 403
    assert as_user("salesman_sunil", "GET", "/orders", params={"retailer_id": patel}).status_code == 403
    visit = {"id": str(uuid.uuid4()), "retailer_id": patel, "started_at": datetime.now(UTC).isoformat()}
    assert as_user("salesman_sunil", "POST", "/salesman/visits", json=visit).status_code == 403
    patel_order = data(as_user("salesman_deepak", "POST", "/orders", json=order_body(PATEL, (BS075, 1))), 201)
    assert as_user("salesman_sunil", "GET", f"/orders/{patel_order['id']}").status_code == 403


# ---------------------------------------------------------------- orders


def test_online_salesman_order_is_attributed_and_in_the_common_order_system(as_user):
    cid = client_id()
    order = data(as_user("salesman_sunil", "POST", "/orders", json=order_body(SHARMA, (BS075, 2), client_order_id=cid)), 201)
    assert (order["source"], order["retailer"]["id"], order["client_order_id"]) == ("SALESMAN", str(SHARMA), cid)
    assert order["created_by"] == {"id": str(SUNIL), "name": "Sunil Yadav", "role": "SALESMAN"}
    assert order["created_offline"] is False and order["status"] == "PENDING"  # waits for the order desk
    # The retailer and the order desk see the same order.
    assert data(as_user("retailer_sharma", "GET", f"/orders/{order['id']}"))["id"] == order["id"]
    assert data(as_user("order_desk", "GET", f"/orders/{order['id']}"))["created_by"]["name"] == "Sunil Yadav"
    # Salesman history shows only orders he created.
    mine = data(as_user("salesman_sunil", "GET", "/orders", params={"created_by_me": "true", "limit": 100}))["items"]
    assert [o["id"] for o in mine] == [order["id"]]
    retailer_orders = data(as_user("retailer_sharma", "POST", "/orders", json={"items": [{"product_id": str(BS075), "quantity": 1, "unit": "case"}]}), 201)
    mine = data(as_user("salesman_sunil", "GET", "/orders", params={"created_by_me": "true", "limit": 100}))["items"]
    assert retailer_orders["id"] not in {o["id"] for o in mine}


def test_retrying_a_sync_never_creates_a_duplicate(as_user, tx):
    cid = client_id()
    body = order_body(SHARMA, (BS075, 2), client_order_id=cid, created_offline=True,
                      client_created_at=(datetime.now(UTC) - timedelta(hours=2)).isoformat())
    first = data(as_user("salesman_sunil", "POST", "/orders", json=body), 201)
    second = data(as_user("salesman_sunil", "POST", "/orders", json=body), 201)
    third = data(as_user("salesman_sunil", "POST", "/orders", json=body), 201)
    assert first["id"] == second["id"] == third["id"]
    assert tx.scalar(select(func.count()).select_from(Order).where(Order.client_order_id == cid)) == 1
    assert first["created_offline"] is True and first["client_created_at"] is not None


def test_another_users_client_order_id_is_refused(as_user):
    cid = client_id()
    data(as_user("salesman_sunil", "POST", "/orders", json=order_body(SHARMA, (BS075, 1), client_order_id=cid)), 201)
    response = as_user("salesman_deepak", "POST", "/orders", json=order_body(PATEL, (BS075, 1), client_order_id=cid))
    assert response.status_code == 409


def test_offline_order_with_changed_price_is_held_for_review_not_changed(as_user, tx):
    tx.execute(update(RetailerPrice).where(RetailerPrice.retailer_id == SHARMA, RetailerPrice.product_id == BS075)
               .values(dealer_price=Decimal("8.50")))  # price went up after the salesman's last sync
    tx.commit()
    body = order_body(SHARMA, (BS075, 2, "8.10"), client_order_id=client_id(), created_offline=True)
    order = data(as_user("salesman_sunil", "POST", "/orders", json=body), 201)
    assert order["status"] == "ON_HOLD"
    assert "price changed from Rs 8.10 to Rs 8.50" in order["hold_reason"]
    assert order["items"][0]["paid_quantity"] == "2.000"  # what the salesman entered is kept


def test_offline_order_short_of_stock_is_held_not_refused(as_user, tx):
    tx.execute(update(Inventory).where(Inventory.product_id == DT1KG).values(stock_cases=1))
    tx.commit()
    body = order_body(SHARMA, (DT1KG, 3, "101.50"), client_order_id=client_id(), created_offline=True)
    order = data(as_user("salesman_sunil", "POST", "/orders", json=body), 201)
    assert order["status"] == "ON_HOLD" and "SKU-DT-1KG: 3 cases needed (incl. free), 1 in stock" in order["hold_reason"]
    # The same order placed online is refused as before.
    online = as_user("salesman_sunil", "POST", "/orders", json=order_body(SHARMA, (DT1KG, 3)))
    assert (online.status_code, online.json()["error_code"]) == (409, "INSUFFICIENT_STOCK")


def test_offline_order_over_credit_goes_to_credit_hold_for_the_desk(as_user):
    body = order_body(SHARMA, (BS075, 25, "8.10"), client_order_id=client_id(), created_offline=True)  # 20,412 > 15,000
    order = data(as_user("salesman_sunil", "POST", "/orders", json=body), 201)
    assert order["status"] == "CREDIT_HOLD"


def test_unchanged_offline_order_is_reviewed_like_an_online_one(as_user):
    body = order_body(SHARMA, (BS075, 2, "8.10"), client_order_id=client_id(), created_offline=True)
    order = data(as_user("salesman_sunil", "POST", "/orders", json=body), 201)
    assert order["status"] == "PENDING" and order["hold_reason"] is None


def test_unavailable_product_fails_clearly(as_user, tx):
    from app.models import Product
    tx.execute(update(Product).where(Product.id == BS075).values(is_active=False))
    tx.commit()
    response = as_user("salesman_sunil", "POST", "/orders",
                       json=order_body(SHARMA, (BS075, 1, "8.10"), client_order_id=client_id(), created_offline=True))
    assert (response.status_code, response.json()["error_code"]) == (404, "PRODUCT_NOT_FOUND")


# ---------------------------------------------------------------- visits


def test_visit_without_order_and_retry_is_one_visit(as_user, tx):
    visit_id = str(uuid.uuid4())
    start = datetime.now(UTC) - timedelta(minutes=20)
    body = {"id": visit_id, "retailer_id": str(SHARMA), "started_at": start.isoformat()}
    data(as_user("salesman_sunil", "POST", "/salesman/visits", json=body))
    ended = {**body, "ended_at": datetime.now(UTC).isoformat(), "outcome": "NO_ORDER"}
    data(as_user("salesman_sunil", "POST", "/salesman/visits", json=ended))
    v = data(as_user("salesman_sunil", "POST", "/salesman/visits", json=ended))  # retried
    assert v["outcome"] == "NO_ORDER" and v["order_id"] is None
    assert tx.scalar(select(func.count()).select_from(ShopVisit).where(ShopVisit.id == uuid.UUID(visit_id))) == 1


def test_visit_links_the_order_placed_during_it(as_user):
    cid = client_id()
    order = data(as_user("salesman_sunil", "POST", "/orders", json=order_body(SHARMA, (BS075, 1), client_order_id=cid)), 201)
    body = {"id": str(uuid.uuid4()), "retailer_id": str(SHARMA), "started_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
            "ended_at": datetime.now(UTC).isoformat(), "outcome": "ORDER_PLACED", "client_order_id": cid}
    v = data(as_user("salesman_sunil", "POST", "/salesman/visits", json=body))
    assert (v["outcome"], v["order_id"]) == ("ORDER_PLACED", order["id"])


def test_visit_validation_and_ownership(as_user):
    now = datetime.now(UTC)
    bad = {"id": str(uuid.uuid4()), "retailer_id": str(SHARMA), "started_at": now.isoformat(),
           "ended_at": (now - timedelta(hours=1)).isoformat()}
    assert as_user("salesman_sunil", "POST", "/salesman/visits", json=bad).status_code == 422
    assert as_user("retailer_sharma", "POST", "/salesman/visits",
                   json={"id": str(uuid.uuid4()), "retailer_id": str(SHARMA), "started_at": now.isoformat()}).status_code == 403


# ---------------------------------------------------------------- data from the API


def test_bundle_shows_retailers_registered_login_mobile(as_user, tx):
    from app.models import User
    # The retailer's login phone can differ from the shop's contact number.
    tx.execute(update(User).where(User.id == seed_id("user", "retailer_sharma")).values(phone="6376169979"))
    tx.commit()
    bundle = data(as_user("salesman_sunil", "GET", "/salesman/sync-bundle"))
    sharma = next(r for r in bundle["retailers"] if r["id"] == str(SHARMA))
    assert (sharma["phone"], sharma["registered_mobiles"]) == ("9000000101", ["6376169979"])
    jain = next(r for r in bundle["retailers"] if r["id"] == str(JAIN))
    assert jain["registered_mobiles"] == []  # no login account


def test_home_counts_come_from_the_server(as_user):
    before = data(as_user("salesman_sunil", "GET", "/salesman/home"))
    assert before["assigned_retailers"] == 3
    data(as_user("salesman_sunil", "POST", "/orders", json=order_body(SHARMA, (BS075, 1), client_order_id=client_id())), 201)
    visit = {"id": str(uuid.uuid4()), "retailer_id": str(GUPTA), "started_at": datetime.now(UTC).isoformat(),
             "ended_at": datetime.now(UTC).isoformat(), "outcome": "NO_ORDER"}
    data(as_user("salesman_sunil", "POST", "/salesman/visits", json=visit))
    after = data(as_user("salesman_sunil", "GET", "/salesman/home"))
    assert after["orders_today"] == before["orders_today"] + 1
    assert after["visits_today"] == before["visits_today"] + 1
    assert any(v["id"] == visit["id"] and v["shop_name"] == "Gupta General Store" and v["outcome"] == "NO_ORDER"
               for v in after["todays_visits"])
    # Other salesmen see only their own.
    assert data(as_user("salesman_deepak", "GET", "/salesman/home"))["visits_today"] == 0
    assert as_user("retailer_sharma", "GET", "/salesman/home").status_code == 403


# ---------------------------------------------------------------- scheme changes while offline


def test_offline_order_with_changed_scheme_is_held_for_review(as_user, tx):
    from app.models import Scheme
    bundle = data(as_user("salesman_sunil", "GET", "/salesman/sync-bundle"))
    shown = [s["id"] for p in bundle["products"] if p["sku"] == "SKU-BS-075" for s in p["schemes"]]
    assert len(shown) == 1  # "Buy 10 get 1 free" was on the phone
    tx.execute(update(Scheme).where(Scheme.product_id == BS075).values(is_active=False))  # ended while offline
    tx.commit()
    body = {"retailer_id": str(SHARMA), "client_order_id": client_id(), "created_offline": True,
            "items": [{"product_id": str(BS075), "quantity": 10, "unit": "case", "expected_unit_price": "8.10",
                       "expected_scheme_ids": shown}]}
    order = data(as_user("salesman_sunil", "POST", "/orders", json=body), 201)
    assert order["status"] == "ON_HOLD"
    assert "SKU-BS-075: scheme changed since the salesman's last sync (Buy 10 get 1 free when ordered, no scheme now)" in order["hold_reason"]
    assert order["items"][0]["paid_quantity"] == "10.000"  # nothing the salesman entered was changed


def test_offline_order_with_unchanged_scheme_is_confirmed(as_user):
    bundle = data(as_user("salesman_sunil", "GET", "/salesman/sync-bundle"))
    shown = [s["id"] for p in bundle["products"] if p["sku"] == "SKU-BS-075" for s in p["schemes"]]
    body = {"retailer_id": str(SHARMA), "client_order_id": client_id(), "created_offline": True,
            "items": [{"product_id": str(BS075), "quantity": 10, "unit": "case", "expected_unit_price": "8.10",
                       "expected_scheme_ids": shown}]}
    order = data(as_user("salesman_sunil", "POST", "/orders", json=body), 201)
    assert order["status"] == "PENDING" and order["items"][0]["scheme"]["description"] == "Buy 10 get 1 free"


def test_new_scheme_since_sync_is_also_flagged(as_user, tx):
    body = {"retailer_id": str(SHARMA), "client_order_id": client_id(), "created_offline": True,
            "items": [{"product_id": str(BS075), "quantity": 10, "unit": "case", "expected_unit_price": "8.10",
                       "expected_scheme_ids": []}]}  # the phone showed no scheme, but one applies now
    order = data(as_user("salesman_sunil", "POST", "/orders", json=body), 201)
    assert order["status"] == "ON_HOLD" and "(no scheme when ordered, Buy 10 get 1 free now)" in order["hold_reason"]


def test_scheme_change_that_does_not_affect_the_quantity_is_not_flagged(as_user, tx):
    from app.models import Scheme
    bundle = data(as_user("salesman_sunil", "GET", "/salesman/sync-bundle"))
    shown = [s["id"] for p in bundle["products"] if p["sku"] == "SKU-DT-1KG" for s in p["schemes"]]  # 3% off on 5+
    tx.execute(update(Scheme).where(Scheme.product_id == DT1KG).values(is_active=False))
    tx.commit()
    body = {"retailer_id": str(SHARMA), "client_order_id": client_id(), "created_offline": True,
            "items": [{"product_id": str(DT1KG), "quantity": 2, "unit": "case", "expected_unit_price": "101.50",
                       "expected_scheme_ids": shown}]}  # 2 cases never qualified for "5+"
    assert data(as_user("salesman_sunil", "POST", "/orders", json=body), 201)["status"] == "PENDING"
