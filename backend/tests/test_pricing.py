"""Pure pricing-engine calculations (no database)."""

import uuid
from dataclasses import dataclass
from decimal import Decimal

import pytest

from app.exceptions.base import AppException
from app.modules.pricing.service import calculate_line, calculate_totals


@dataclass
class FakeScheme:
    scheme_type: str
    min_quantity: Decimal
    free_quantity: Decimal = Decimal("0")
    discount_percentage: Decimal = Decimal("0")
    id: uuid.UUID = uuid.uuid4()


BUY_10_GET_1 = FakeScheme("FREE_GOODS", Decimal("10"), free_quantity=Decimal("1"))
FIVE_PLUS_3_PCT = FakeScheme("SLAB_DISCOUNT", Decimal("5"), discount_percentage=Decimal("3"))


def biscuit(quantity, schemes=(BUY_10_GET_1,), **overrides):
    """SKU-BS-075 as seeded for Sharma: ₹8.10 per piece, 96 per case, GST 5%, GST extra."""
    args = dict(
        quantity=Decimal(quantity), dealer_price=Decimal("8.10"), price_basis="PIECE",
        tax_inclusive=False, units_per_case=Decimal("96"), gst_rate=Decimal("5"),
        schemes=list(schemes),
    )
    args.update(overrides)
    return calculate_line(**args)


def detergent(quantity):
    """SKU-DT-1KG for Sharma: ₹101.50 per piece, 20 per case, GST 18%, 3% off at 5+ cases."""
    return calculate_line(
        quantity=Decimal(quantity), dealer_price=Decimal("101.50"), price_basis="PIECE",
        tax_inclusive=False, units_per_case=Decimal("20"), gst_rate=Decimal("18"),
        schemes=[FIVE_PLUS_3_PCT],
    )


@pytest.mark.parametrize("cases, free", [(9, 0), (10, 1), (11, 1), (19, 1), (20, 2), (25, 2)])
def test_free_goods_per_full_multiple(cases, free):
    line = biscuit(cases)
    assert line.paid_quantity == cases
    assert line.free_quantity == free
    assert line.discount_amount == 0


def test_free_goods_amounts_charge_only_paid_cases():
    line = biscuit(10)
    # 10 cases x 96 pieces x ₹8.10 = ₹7,776.00; GST 5% = ₹388.80
    assert (line.taxable_amount, line.gst_amount, line.line_total) == (
        Decimal("7776.00"), Decimal("388.80"), Decimal("8164.80"),
    )


@pytest.mark.parametrize("cases, pct", [(4, 0), (5, 3), (6, 3)])
def test_slab_discount_threshold(cases, pct):
    line = detergent(cases)
    assert line.discount_percentage == pct
    assert line.free_quantity == 0


def test_slab_discount_amounts():
    line = detergent(5)
    # 5 x 20 x 101.50 = 10,150.00; 3% = 304.50; taxable 9,845.50; GST 18% = 1,772.19
    assert (line.discount_amount, line.taxable_amount, line.gst_amount, line.line_total) == (
        Decimal("304.50"), Decimal("9845.50"), Decimal("1772.19"), Decimal("11617.69"),
    )


def test_case_price_basis_is_not_multiplied_by_units_per_case():
    per_case = biscuit(10, dealer_price=Decimal("777.60"), price_basis="CASE")
    per_piece = biscuit(10)
    assert per_case.taxable_amount == per_piece.taxable_amount == Decimal("7776.00")
    assert per_case.unit_price == Decimal("777.60") and per_case.price_basis == "CASE"


def test_tax_inclusive_price_extracts_gst():
    line = biscuit(1, schemes=(), dealer_price=Decimal("1050"), price_basis="CASE", tax_inclusive=True)
    assert (line.taxable_amount, line.gst_amount, line.line_total) == (
        Decimal("1000.00"), Decimal("50.00"), Decimal("1050.00"),
    )


def test_two_qualifying_schemes_are_not_combined():
    with pytest.raises(AppException) as exc:
        biscuit(10, schemes=(BUY_10_GET_1, FakeScheme("SLAB_DISCOUNT", Decimal("5"), discount_percentage=Decimal("2"))))
    assert exc.value.error_code == "SCHEME_CONFLICT"


def test_only_qualifying_scheme_applies_when_another_is_not_reached():
    line = biscuit(6, schemes=(BUY_10_GET_1, FakeScheme("SLAB_DISCOUNT", Decimal("5"), discount_percentage=Decimal("2"))))
    assert (line.free_quantity, line.discount_percentage) == (0, 2)


def test_quantity_must_be_positive():
    with pytest.raises(AppException):
        biscuit(0)


def test_order_totals_are_consistent():
    totals = calculate_totals([biscuit(10), detergent(5)])
    assert totals.subtotal - totals.discount_total == totals.taxable_amount
    assert totals.taxable_amount + totals.gst_amount == totals.grand_total
    assert totals.grand_total == Decimal("8164.80") + Decimal("11617.69")
