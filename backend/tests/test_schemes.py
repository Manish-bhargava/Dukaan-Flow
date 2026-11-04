"""Scheme engine (pure, no database): eligibility, dates, both V1 scheme types, conflicts."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.exceptions.base import AppException
from app.modules.schemes import engine

NOW = datetime(2026, 11, 4, 12, tzinfo=UTC)


@dataclass
class Scheme:
    scheme_type: str
    min_quantity: Decimal
    free_quantity: Decimal = Decimal("0")
    discount_percentage: Decimal = Decimal("0")
    is_active: bool = True
    starts_at: datetime = NOW - timedelta(days=30)
    ends_at: datetime | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


def buy_10_get_1(**kw):
    return Scheme("FREE_GOODS", Decimal("10"), free_quantity=Decimal("1"), **kw)


def detergent_3_pct(**kw):
    return Scheme("SLAB_DISCOUNT", Decimal("5"), discount_percentage=Decimal("3"), **kw)


# ---------------------------------------------------------------- buy X get Y free


@pytest.mark.parametrize("cases, free", [
    (1, None), (9, None), (10, 1), (11, 1), (19, 1), (20, 2), (25, 2), (29, 2), (30, 3), (100, 10),
])
def test_buy_10_get_1_counts_full_sets_only(cases, free):
    benefit = engine.evaluate(Decimal(cases), [buy_10_get_1()])
    if free is None:
        assert benefit is None
    else:
        assert benefit.free_quantity == free and benefit.discount_percentage == 0


def test_spec_example_25_cases_gives_2_free_27_supplied():
    benefit = engine.evaluate(Decimal(25), [buy_10_get_1()])
    assert (Decimal(25), benefit.free_quantity, Decimal(25) + benefit.free_quantity) == (25, 2, 27)


def test_buy_x_get_y_with_larger_y():
    benefit = engine.evaluate(Decimal(13), [Scheme("FREE_GOODS", Decimal("6"), free_quantity=Decimal("2"))])
    assert benefit.free_quantity == 4  # 2 full sets of 6


# ---------------------------------------------------------------- slab discount


@pytest.mark.parametrize("cases, pct", [(1, None), (4, None), (5, 3), (6, 3), (50, 3)])
def test_slab_discount_from_threshold(cases, pct):
    benefit = engine.evaluate(Decimal(cases), [detergent_3_pct()])
    assert (benefit.discount_percentage if benefit else None) == pct
    if benefit:
        assert benefit.free_quantity == 0


def test_fractional_quantity_just_below_threshold_does_not_qualify():
    assert engine.evaluate(Decimal("4.999"), [detergent_3_pct()]) is None


# ---------------------------------------------------------------- eligibility and dates


def test_inactive_and_out_of_window_schemes_are_excluded():
    active = buy_10_get_1()
    candidates = [
        active,
        buy_10_get_1(is_active=False),
        buy_10_get_1(starts_at=NOW + timedelta(seconds=1)),  # not started yet
        buy_10_get_1(ends_at=NOW - timedelta(days=1)),  # expired
        buy_10_get_1(ends_at=NOW),  # ends exactly now: end is exclusive
    ]
    assert engine.active_schemes(candidates, NOW) == [active]


def test_scheme_starting_exactly_now_applies():
    scheme = buy_10_get_1(starts_at=NOW)
    assert engine.active_schemes([scheme], NOW) == [scheme]


def test_two_qualifying_schemes_are_refused_not_combined():
    with pytest.raises(AppException) as exc:
        engine.evaluate(Decimal(10), [buy_10_get_1(), detergent_3_pct()])
    assert exc.value.error_code == "SCHEME_CONFLICT"


def test_only_the_reached_scheme_applies():
    benefit = engine.evaluate(Decimal(6), [buy_10_get_1(), detergent_3_pct()])
    assert benefit.scheme_type == "SLAB_DISCOUNT"


def test_unknown_scheme_type_is_ignored_not_misapplied():
    assert engine.evaluate(Decimal(10), [Scheme("CASHBACK", Decimal("1"))]) is None


# ---------------------------------------------------------------- description and snapshot


def test_descriptions_and_snapshot():
    free = engine.evaluate(Decimal(25), [buy_10_get_1()])
    slab = engine.evaluate(Decimal(5), [detergent_3_pct()])
    assert free.description == "Buy 10 get 1 free"
    assert slab.description == "3% off on 5+"
    snap = free.snapshot()
    assert snap["scheme_type"] == "FREE_GOODS" and snap["free_quantity"] == "2"
    assert snap["description"] == "Buy 10 get 1 free" and snap["scheme_id"] == str(free.scheme_id)
