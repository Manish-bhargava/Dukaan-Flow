"""Retailer data isolation enforced in the service layer."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.exceptions.base import AppException
from app.models import Retailer
from app.modules.orders import service as orders
from app.modules.orders.schemas import CreateOrderInput, OrderItemInput
from app.modules.pricing import service as pricing
from app.modules.retailers import service as retailers
from seed.run_seed import seed_id
from tests.conftest import seed_user

SHARMA, GUPTA, JAIN, PATEL = (seed_id("retailer", k) for k in ("sharma", "gupta", "jain", "patel"))
BS075 = seed_id("product", "SKU-BS-075")


@pytest.fixture
def orders_by_retailer(tx):
    created = {}
    for user_key, retailer_id in [("retailer_sharma", SHARMA), ("retailer_gupta", GUPTA),
                                  ("salesman_deepak", PATEL)]:
        created[retailer_id] = orders.create_order(tx, seed_user(tx, user_key), CreateOrderInput(
            retailer_id=retailer_id, items=[OrderItemInput(product_id=BS075, quantity=Decimal(1), unit="case")]))
    return created


def forbidden(callable_, *args):
    with pytest.raises(AppException) as exc:
        callable_(*args)
    return exc.value.error_code == "FORBIDDEN"


def test_retailer_cannot_read_another_retailers_order(tx, orders_by_retailer):
    gupta = seed_user(tx, "retailer_gupta")
    assert orders.get_order(tx, gupta, orders_by_retailer[GUPTA].id).retailer_id == GUPTA
    assert forbidden(orders.get_order, tx, gupta, orders_by_retailer[SHARMA].id)


def test_order_lists_are_scoped_by_role(tx, orders_by_retailer):
    def visible(user_key):
        return {o.retailer_id for o in orders.list_orders(tx, seed_user(tx, user_key))}

    assert visible("retailer_sharma") == {SHARMA}
    assert visible("salesman_sunil") == {SHARMA, GUPTA}  # assigned: Sharma, Gupta, Jain
    assert visible("salesman_deepak") == {PATEL}
    assert visible("order_desk") == visible("admin") == {SHARMA, GUPTA, PATEL}


def test_salesman_cannot_read_unassigned_retailers_order(tx, orders_by_retailer):
    assert forbidden(orders.get_order, tx, seed_user(tx, "salesman_sunil"), orders_by_retailer[PATEL].id)


def test_credit_information_is_private(tx):
    assert retailers.get_credit_summary(tx, seed_user(tx, "retailer_sharma"), SHARMA).available_credit == Decimal("15000.00")
    assert forbidden(retailers.get_credit_summary, tx, seed_user(tx, "retailer_gupta"), SHARMA)
    assert forbidden(retailers.get_credit_summary, tx, seed_user(tx, "salesman_deepak"), SHARMA)
    assert retailers.get_credit_summary(tx, seed_user(tx, "order_desk"), SHARMA).credit_limit == Decimal("50000.00")


def test_retailer_prices_are_private(tx):
    sharma = tx.get(Retailer, SHARMA)
    now = datetime.now(UTC)
    own = pricing.get_retailer_prices(tx, seed_user(tx, "retailer_sharma"), sharma, now)
    assert own[BS075].dealer_price == Decimal("8.10")
    assert forbidden(pricing.get_retailer_prices, tx, seed_user(tx, "retailer_gupta"), sharma, now)


def test_inactive_user_has_no_access(tx):
    user = seed_user(tx, "order_desk")
    user.is_active = False
    assert forbidden(retailers.get_credit_summary, tx, user, SHARMA)
