"""GET /products and /products/categories: the retailer's own catalogue view."""

from decimal import Decimal

import pytest

from app.core.security import create_access_token
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
def test_staff_cannot_use_retailer_catalogue(tx_client, tx, key):
    for url in (URL, f"{URL}/categories"):
        response = get(tx_client, tx, key, url=url)
        assert (response.status_code, response.json()["error_code"]) == (403, "FORBIDDEN")


def test_catalogue_requires_login(tx_client):
    response = tx_client.get(URL)
    assert (response.status_code, response.json()["error_code"]) == (401, "UNAUTHORIZED")


@pytest.mark.parametrize("params", [{"page": 0}, {"limit": 101}, {"category_id": "nope"}])
def test_invalid_query_is_rejected(tx_client, tx, params):
    assert get(tx_client, tx, **params).status_code == 422
