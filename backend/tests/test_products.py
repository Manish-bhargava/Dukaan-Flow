"""GET /products and /products/categories: the retailer's own catalogue view."""

from decimal import Decimal

import pytest
from sqlalchemy import update

from app.core.security import create_access_token
from app.models import Scheme
from seed.run_seed import seed_id
from tests.conftest import seed_user

URL = "/api/v1/products"


def auth(tx, key: str) -> dict:
    token, _ = create_access_token(seed_user(tx, key))
    return {"Authorization": f"Bearer {token}"}


def get(client, tx, key="retailer_sharma", url=URL, **params):
    return client.get(url, headers=auth(tx, key), params=params)


def by_sku(response) -> dict:
    return {item["sku"]: item for item in response.json()["data"]["items"]}


def test_retailer_sees_own_prices_stock_and_active_schemes(tx_client, tx):
    response = get(tx_client, tx, limit=100)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["page"] == 1 and data["total"] == len(data["items"]) > 0
    items = by_sku(response)

    biscuit = items["SKU-BS-075"]
    assert biscuit["category"]["name"] == "Biscuits"
    assert biscuit["order_unit"] == "case"
    # Current price, not the expired 7.90 one.
    assert Decimal(biscuit["price"]["dealer_price"]) != Decimal("7.90")
    if biscuit["price"]["price_basis"] == "PIECE":
        expected = Decimal(biscuit["price"]["dealer_price"]) * Decimal(biscuit["units_per_case"])
        assert Decimal(biscuit["price"]["case_price"]) == expected.quantize(Decimal("0.01"))
    assert [s["scheme_type"] for s in biscuit["schemes"]] == ["FREE_GOODS"]

    assert items["SKU-TE-250"]["in_stock"] is False  # seeded with 0 cases
    assert items["SKU-NS-070"]["schemes"] == []  # its only scheme has expired


def test_retailers_get_different_prices(tx_client, tx):
    sharma = by_sku(get(tx_client, tx, "retailer_sharma", limit=100))
    gupta = by_sku(get(tx_client, tx, "retailer_gupta", limit=100))
    assert any(sharma[s]["price"] != gupta[s]["price"] for s in sharma.keys() & gupta.keys())


def test_search_category_filter_and_pagination(tx_client, tx):
    assert set(by_sku(get(tx_client, tx, search="detergent"))) == {"SKU-DT-1KG", "SKU-DT-500", "SKU-DB-150"}

    categories = get(tx_client, tx, url=f"{URL}/categories").json()["data"]
    tea = next(c for c in categories if c["name"] == "Tea")
    assert set(by_sku(get(tx_client, tx, category_id=tea["id"]))) == {"SKU-TE-250", "SKU-TE-500"}

    first = get(tx_client, tx, limit=3, page=1).json()["data"]
    second = get(tx_client, tx, limit=3, page=2).json()["data"]
    assert len(first["items"]) == 3 and first["total"] == second["total"]
    assert {i["id"] for i in first["items"]}.isdisjoint(i["id"] for i in second["items"])


@pytest.mark.parametrize("key", ["order_desk", "admin", "salesman_sunil"])
def test_staff_must_name_a_retailer(tx_client, tx, key):
    response = get(tx_client, tx, key)
    assert (response.status_code, response.json()["error_code"]) == (422, "VALIDATION_ERROR")


def test_order_desk_sees_a_named_retailers_prices(tx_client, tx):
    gupta = str(seed_id("retailer", "gupta"))
    as_desk = by_sku(get(tx_client, tx, "order_desk", retailer_id=gupta, limit=100))
    as_gupta = by_sku(get(tx_client, tx, "retailer_gupta", limit=100))
    assert as_desk == as_gupta


def test_retailer_cannot_see_another_retailers_prices(tx_client, tx):
    response = get(tx_client, tx, "retailer_sharma", retailer_id=str(seed_id("retailer", "gupta")))
    assert (response.status_code, response.json()["error_code"]) == (403, "FORBIDDEN")


def test_salesman_only_sees_assigned_retailers(tx_client, tx):
    # Sharma is assigned to Sunil, not Deepak.
    sharma = str(seed_id("retailer", "sharma"))
    assert get(tx_client, tx, "salesman_deepak", retailer_id=sharma).status_code == 403


def test_catalogue_requires_login(tx_client):
    response = tx_client.get(URL)
    assert (response.status_code, response.json()["error_code"]) == (401, "UNAUTHORIZED")


@pytest.mark.parametrize("params", [{"page": 0}, {"limit": 101}, {"category_id": "nope"}])
def test_invalid_query_is_rejected(tx_client, tx, params):
    assert get(tx_client, tx, **params).status_code == 422


def test_has_scheme_lists_only_products_on_offer(tx_client, tx):
    offers = get(tx_client, tx, has_scheme="true", limit=100)
    assert offers.status_code == 200
    items = by_sku(offers)
    # Seeded: biscuit 75g buy 10 get 1, detergent 1kg 3% off at 5+; the noodles scheme has expired.
    assert set(items) == {"SKU-BS-075", "SKU-DT-1KG"}
    assert offers.json()["data"]["total"] == 2
    assert all(item["schemes"] for item in items.values())
    assert items["SKU-BS-075"]["schemes"][0]["description"] == "Buy 10 get 1 free"


def test_has_scheme_excludes_inactive_schemes(tx_client, tx):
    tx.execute(update(Scheme).where(Scheme.product_id == seed_id("product", "SKU-DT-1KG")).values(is_active=False))
    assert set(by_sku(get(tx_client, tx, has_scheme="true", limit=100))) == {"SKU-BS-075"}
