"""Order creation, Order Desk corrections, credit holds, approval and rejection (real PostgreSQL)."""

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.exceptions.base import AppException
from app.models import (
    CreditAccount,
    CreditLedger,
    Inventory,
    Order,
    OrderCorrection,
    RetailerAlias,
    RetailerPrice,
    StockMovement,
)
from app.modules.orders import service as orders
from app.modules.orders.schemas import CorrectOrderItemInput, CreateOrderInput, OrderItemInput
from app.modules.retailers import repository as retailer_repository
from seed.run_seed import seed_id
from tests.conftest import seed_user

SHARMA, GUPTA, JAIN, PATEL = (seed_id("retailer", k) for k in ("sharma", "gupta", "jain", "patel"))
BS075, BS150, DT1KG, DW500, TE250 = (
    seed_id("product", s) for s in ("SKU-BS-075", "SKU-BS-150", "SKU-DT-1KG", "SKU-DW-500", "SKU-TE-250")
)


def item(product_id, quantity, unit="case"):
    return OrderItemInput(product_id=product_id, quantity=Decimal(quantity), unit=unit)


def place(tx, user_key, *items, retailer_id=None):
    return orders.create_order(
        tx, seed_user(tx, user_key), CreateOrderInput(retailer_id=retailer_id, items=list(items))
    )


def error_code(callable_, *args, **kwargs):
    with pytest.raises(AppException) as exc:
        callable_(*args, **kwargs)
    return exc.value.error_code


def stock(tx, product_id):
    return tx.scalar(select(Inventory.stock_cases).where(Inventory.product_id == product_id))


def credit(tx, retailer_id):
    return tx.scalar(select(CreditAccount).where(CreditAccount.retailer_id == retailer_id))


def count(tx, model, *where):
    return tx.scalar(select(func.count()).select_from(model).where(*where))


# ------------------------------------------------------------ creation


def test_retailer_creates_manual_order_with_backend_pricing(tx):
    order = place(tx, "retailer_sharma", item(BS075, 10))
    [line] = order.items
    assert (order.source, order.status, order.retailer_id) == ("MANUAL", "PENDING", SHARMA)
    assert order.created_by == seed_id("user", "retailer_sharma")
    assert (line.sku, line.paid_quantity, line.free_quantity) == ("SKU-BS-075", 10, 1)
    assert (line.unit_price, line.price_basis, line.gst_rate) == (Decimal("8.10"), "PIECE", Decimal("5"))
    assert (order.taxable_amount, order.gst_amount, order.grand_total) == (
        Decimal("7776.00"), Decimal("388.80"), Decimal("8164.80"),
    )
    assert order.order_number.startswith("DF-")


def test_order_keeps_price_snapshot_when_price_changes_later(tx):
    order = place(tx, "retailer_sharma", item(BS075, 10))
    price = tx.scalar(select(RetailerPrice).where(
        RetailerPrice.retailer_id == SHARMA, RetailerPrice.product_id == BS075,
        RetailerPrice.effective_to.is_(None),
    ))
    price.dealer_price = Decimal("99.99")
    tx.flush()
    tx.expire_all()
    reloaded = tx.get(Order, order.id)
    assert reloaded.items[0].unit_price == Decimal("8.10")
    assert reloaded.grand_total == Decimal("8164.80")


def test_order_over_available_credit_goes_on_credit_hold(tx):
    # 8,164.80 + 11,617.69 = 19,782.49 > Sharma's available credit of 15,000
    order = place(tx, "retailer_sharma", item(BS075, 10), item(DT1KG, 5))
    assert order.status == "CREDIT_HOLD"
    assert order.grand_total == Decimal("19782.49")


def test_out_of_stock_product_cannot_be_ordered(tx):
    assert error_code(place, tx, "retailer_sharma", item(TE250, 1)) == "INSUFFICIENT_STOCK"
    assert count(tx, Order) == 0


def test_stock_validation_includes_free_goods(tx):
    # 340 cases in stock; ordering 340 earns 34 free -> 374 needed
    assert error_code(place, tx, "retailer_gupta", item(BS075, 340)) == "INSUFFICIENT_STOCK"


def test_unit_must_match_product_order_unit(tx):
    assert error_code(place, tx, "retailer_sharma", item(BS075, 10, unit="piece")) == "VALIDATION_ERROR"


def test_retailer_cannot_order_for_another_retailer(tx):
    assert error_code(place, tx, "retailer_sharma", item(BS075, 1), retailer_id=GUPTA) == "FORBIDDEN"


def test_salesman_orders_only_for_assigned_retailers(tx):
    order = place(tx, "salesman_deepak", item(BS075, 1), retailer_id=PATEL)
    assert order.source == "SALESMAN"
    assert error_code(place, tx, "salesman_sunil", item(BS075, 1), retailer_id=PATEL) == "FORBIDDEN"


@pytest.mark.parametrize("user_key", ["order_desk", "admin"])
def test_order_desk_and_admin_do_not_place_orders(tx, user_key):
    assert error_code(place, tx, user_key, item(BS075, 1), retailer_id=SHARMA) == "FORBIDDEN"


# ------------------------------------------------------------ corrections


def correct(tx, user_key, order, **changes):
    return orders.correct_order_item(
        tx, seed_user(tx, user_key), order.id, order.items[0].id, CorrectOrderItemInput(**changes)
    )


def test_order_desk_corrects_quantity_with_audit_and_repricing(tx):
    order = place(tx, "retailer_gupta", item(BS075, 10))
    correction = correct(tx, "order_desk", order, new_quantity=Decimal("20"), reason="Called retailer")
    assert (correction.old_product_id, correction.new_product_id) == (BS075, BS075)
    assert (correction.old_quantity, correction.new_quantity) == (10, 20)
    assert correction.corrected_by == seed_id("user", "order_desk")
    assert correction.reason == "Called retailer" and correction.created_at is not None
    line = order.items[0]
    assert (line.paid_quantity, line.free_quantity) == (20, 2)
    assert order.grand_total == line.line_total


def test_order_desk_corrects_product_and_saves_retailer_alias(tx):
    order = place(tx, "retailer_gupta", item(BS075, 2))
    correct(tx, "order_desk", order, new_product_id=BS150, reason="Wrong SKU", save_alias="bada wala biscuit")
    assert order.items[0].sku == "SKU-BS-150" and order.items[0].product_id == BS150
    alias = tx.scalar(select(RetailerAlias).where(
        RetailerAlias.retailer_id == GUPTA, RetailerAlias.normalized_alias == "bada wala biscuit"
    ))
    assert alias.product_id == BS150


def test_every_correction_is_kept_in_history(tx):
    order = place(tx, "retailer_gupta", item(BS075, 10))
    correct(tx, "order_desk", order, new_quantity=Decimal("12"))
    correct(tx, "admin", order, new_product_id=BS150)
    history = tx.scalars(
        select(OrderCorrection).where(OrderCorrection.order_item_id == order.items[0].id)
        .order_by(OrderCorrection.new_quantity)
    ).all()
    assert [(h.old_product_id, h.new_product_id, h.old_quantity, h.new_quantity) for h in history] == [
        (BS075, BS075, 10, 12), (BS075, BS150, 12, 12),
    ]


def test_correction_can_move_order_onto_credit_hold(tx):
    order = place(tx, "retailer_sharma", item(DT1KG, 4))  # 9,581.60 <= 15,000
    assert order.status == "PENDING"
    correct(tx, "order_desk", order, new_quantity=Decimal("8"))  # 18,588.30 > 15,000
    assert order.status == "CREDIT_HOLD"


def test_retailer_cannot_correct_orders(tx):
    order = place(tx, "retailer_gupta", item(BS075, 10))
    assert error_code(correct, tx, "retailer_gupta", order, new_quantity=Decimal("5")) == "FORBIDDEN"


def test_correction_refused_for_wrong_unit(tx):
    order = place(tx, "retailer_gupta", item(BS075, 10))
    assert error_code(correct, tx, "order_desk", order, new_quantity=Decimal("5"), unit="piece") == "VALIDATION_ERROR"
    assert count(tx, OrderCorrection) == 0


# ------------------------------------------------------------ approval


def approve(tx, order, user_key="order_desk", **kwargs):
    return orders.approve_order(tx, seed_user(tx, user_key), order.id, **kwargs)


def test_approval_deducts_stock_debits_credit_and_records_everything(tx):
    order = place(tx, "retailer_gupta", item(BS075, 10))
    outstanding_before = credit(tx, GUPTA).current_outstanding
    approve(tx, order)

    assert order.status == "APPROVED"
    assert order.approved_by == seed_id("user", "order_desk") and order.approved_at is not None
    assert stock(tx, BS075) == Decimal("329")  # 340 - (10 paid + 1 free)
    movement = tx.scalar(select(StockMovement).where(StockMovement.order_id == order.id))
    assert (movement.movement_type, movement.quantity, movement.product_id) == ("ORDER_DEDUCTION", -11, BS075)
    ledger = tx.scalar(select(CreditLedger).where(CreditLedger.order_id == order.id))
    assert (ledger.transaction_type, ledger.amount) == ("ORDER_DEBIT", order.grand_total)
    assert credit(tx, GUPTA).current_outstanding == outstanding_before + order.grand_total


def test_admin_can_approve(tx):
    order = place(tx, "retailer_gupta", item(BS075, 1))
    assert approve(tx, order, user_key="admin").status == "APPROVED"


@pytest.mark.parametrize("user_key", ["retailer_gupta", "salesman_sunil"])
def test_retailers_and_salesmen_cannot_approve(tx, user_key):
    order = place(tx, "retailer_gupta", item(BS075, 1))
    assert error_code(approve, tx, order, user_key=user_key) == "FORBIDDEN"


def test_credit_hold_order_is_not_approved_without_override(tx):
    order = place(tx, "retailer_sharma", item(BS075, 10), item(DT1KG, 5))
    assert error_code(approve, tx, order) == "CREDIT_LIMIT_EXCEEDED"
    tx.refresh(order)
    assert order.status == "CREDIT_HOLD"
    assert stock(tx, BS075) == 340
    assert count(tx, CreditLedger, CreditLedger.order_id == order.id) == 0


def test_order_desk_releases_credit_hold_with_recorded_reason(tx):
    order = place(tx, "retailer_sharma", item(BS075, 10), item(DT1KG, 5))
    approve(tx, order, credit_override_reason="Owner approved; payment due Friday")
    assert order.status == "APPROVED"
    ledger = tx.scalar(select(CreditLedger).where(CreditLedger.order_id == order.id))
    assert "Owner approved; payment due Friday" in ledger.description
    assert credit(tx, SHARMA).current_outstanding == Decimal("35000.00") + Decimal("19782.49")


def test_credit_is_rechecked_at_approval_and_order_put_on_hold(tx):
    first = place(tx, "retailer_sharma", item(DT1KG, 4))   # 9,581.60
    second = place(tx, "retailer_sharma", item(DT1KG, 4))  # each fits the 15,000 alone
    assert (first.status, second.status) == ("PENDING", "PENDING")
    approve(tx, first)
    assert error_code(approve, tx, second) == "CREDIT_LIMIT_EXCEEDED"
    tx.refresh(second)
    assert second.status == "CREDIT_HOLD"


def test_stock_is_rechecked_at_approval(tx):
    first = place(tx, "retailer_gupta", item(DW500, 8))  # exactly the 8 cases in stock
    second = place(tx, "salesman_sunil", item(DW500, 8), retailer_id=JAIN)
    approve(tx, first)
    assert error_code(approve, tx, second) == "INSUFFICIENT_STOCK"
    tx.refresh(second)
    assert second.status == "PENDING"
    assert stock(tx, DW500) == 0
    assert count(tx, StockMovement, StockMovement.order_id == second.id) == 0


def test_order_cannot_be_approved_twice(tx):
    order = place(tx, "retailer_gupta", item(BS075, 10))
    approve(tx, order)
    assert error_code(approve, tx, order) == "INVALID_ORDER_STATUS"
    assert stock(tx, BS075) == Decimal("329")


def test_failed_approval_rolls_back_stock_movements_and_status(tx, monkeypatch):
    order = place(tx, "retailer_gupta", item(BS075, 10))
    outstanding_before = credit(tx, GUPTA).current_outstanding

    def fail(*_args, **_kwargs):
        raise RuntimeError("simulated failure while writing the credit ledger")

    monkeypatch.setattr(retailer_repository, "add_ledger_entry", fail)
    with pytest.raises(RuntimeError):
        approve(tx, order)

    tx.refresh(order)
    assert order.status == "PENDING" and order.approved_by is None
    assert stock(tx, BS075) == 340
    assert count(tx, StockMovement, StockMovement.order_id == order.id) == 0
    assert credit(tx, GUPTA).current_outstanding == outstanding_before


def test_approval_refuses_order_whose_totals_do_not_match_items(tx):
    order = place(tx, "retailer_gupta", item(BS075, 10))
    order.grand_total += Decimal("1")
    tx.commit()
    with pytest.raises(AppException):
        approve(tx, order)
    tx.refresh(order)
    assert order.status == "PENDING" and stock(tx, BS075) == 340


# ------------------------------------------------------------ rejection


def test_rejection_stores_reason_without_touching_stock_or_credit(tx):
    order = place(tx, "retailer_gupta", item(BS075, 10))
    outstanding_before = credit(tx, GUPTA).current_outstanding
    orders.reject_order(tx, seed_user(tx, "order_desk"), order.id, "Shop closed this week")
    assert (order.status, order.rejection_reason) == ("REJECTED", "Shop closed this week")
    assert stock(tx, BS075) == 340
    assert count(tx, StockMovement, StockMovement.order_id == order.id) == 0
    assert count(tx, CreditLedger, CreditLedger.order_id == order.id) == 0
    assert credit(tx, GUPTA).current_outstanding == outstanding_before


def test_rejection_requires_reason_and_open_order(tx):
    desk = seed_user(tx, "order_desk")
    order = place(tx, "retailer_gupta", item(BS075, 10))
    assert error_code(orders.reject_order, tx, desk, order.id, "  ") == "VALIDATION_ERROR"
    approve(tx, order)
    assert error_code(orders.reject_order, tx, desk, order.id, "Too late") == "INVALID_ORDER_STATUS"


def test_retailer_cannot_reject(tx):
    order = place(tx, "retailer_gupta", item(BS075, 10))
    assert error_code(orders.reject_order, tx, seed_user(tx, "retailer_gupta"), order.id, "x") == "FORBIDDEN"
