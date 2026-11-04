"""Scheme engine: which scheme applies to an order line and what it gives.

Scheme definitions live in the `schemes` table; this module only evaluates them. It knows
nothing about prices, so pricing (app/modules/pricing) asks it for the benefit and then
does the money arithmetic.

V1 scheme types:
- FREE_GOODS (buy X get Y free): free_quantity cases for every full min_quantity ordered.
  Buy 10 get 1: 9 -> 0, 10 -> 1, 25 -> 2 (paid 25, supplied 27).
- SLAB_DISCOUNT: discount_percentage off the whole line once min_quantity is reached.

Rules:
- Only schemes that are active and inside their start/end window at the pricing time apply.
- Schemes are never combined: if more than one qualifies for the same line, the line is
  refused with SCHEME_CONFLICT so the configuration gets fixed instead of the system choosing.

To add a scheme type: add it to SchemeType, write an evaluator returning a SchemeBenefit
and register it in _EVALUATORS (plus a DB CHECK constraint for its benefit columns).
"""

import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_FLOOR, Decimal
from typing import Protocol

from app.core.constants import ErrorCode, SchemeType
from app.exceptions.base import AppException

ZERO = Decimal("0")


class SchemeLike(Protocol):
    id: uuid.UUID
    scheme_type: str
    min_quantity: Decimal
    free_quantity: Decimal
    discount_percentage: Decimal


class DatedScheme(SchemeLike, Protocol):
    is_active: bool
    starts_at: datetime
    ends_at: datetime | None


@dataclass(frozen=True)
class SchemeBenefit:
    scheme_id: uuid.UUID
    scheme_type: str
    min_quantity: Decimal
    free_quantity: Decimal  # free cases for this line (0 for a discount scheme)
    discount_percentage: Decimal  # 0 for a free-goods scheme
    description: str  # e.g. "Buy 10 get 1 free"

    def snapshot(self) -> dict:
        """Stored on the order item so the order keeps the scheme as it was when applied."""
        return {
            "scheme_id": str(self.scheme_id),
            "scheme_type": self.scheme_type,
            "min_quantity": str(self.min_quantity),
            "free_quantity": str(self.free_quantity),
            "discount_percentage": str(self.discount_percentage),
            "description": self.description,
        }


def _number(value: Decimal) -> str:
    return f"{value.normalize():f}"


def describe(scheme: SchemeLike) -> str:
    if scheme.scheme_type == SchemeType.FREE_GOODS:
        return f"Buy {_number(scheme.min_quantity)} get {_number(scheme.free_quantity)} free"
    if scheme.scheme_type == SchemeType.SLAB_DISCOUNT:
        return f"{_number(scheme.discount_percentage)}% off on {_number(scheme.min_quantity)}+"
    return scheme.scheme_type


def _free_goods(scheme: SchemeLike, quantity: Decimal) -> SchemeBenefit:
    full_sets = (quantity / scheme.min_quantity).to_integral_value(rounding=ROUND_FLOOR)
    return SchemeBenefit(scheme.id, scheme.scheme_type, scheme.min_quantity,
                         full_sets * scheme.free_quantity, ZERO, describe(scheme))


def _slab_discount(scheme: SchemeLike, quantity: Decimal) -> SchemeBenefit:
    return SchemeBenefit(scheme.id, scheme.scheme_type, scheme.min_quantity,
                         ZERO, scheme.discount_percentage, describe(scheme))


_EVALUATORS: dict[str, Callable[[SchemeLike, Decimal], SchemeBenefit]] = {
    SchemeType.FREE_GOODS: _free_goods,
    SchemeType.SLAB_DISCOUNT: _slab_discount,
}


def is_active_at(scheme: DatedScheme, at: datetime) -> bool:
    return scheme.is_active and scheme.starts_at <= at and (scheme.ends_at is None or scheme.ends_at > at)


def active_schemes(schemes: Iterable[DatedScheme], at: datetime) -> list[DatedScheme]:
    return [s for s in schemes if is_active_at(s, at)]


def evaluate(quantity: Decimal, schemes: Sequence[SchemeLike]) -> SchemeBenefit | None:
    """The benefit for `quantity` cases given the product's active schemes (None if none qualifies)."""
    qualifying = [s for s in schemes if s.scheme_type in _EVALUATORS and quantity >= s.min_quantity]
    if len(qualifying) > 1:
        raise AppException(
            "More than one scheme applies to this product; schemes cannot be combined",
            ErrorCode.SCHEME_CONFLICT,
            status_code=409,
            details={"scheme_ids": [str(s.id) for s in qualifying]},
        )
    if not qualifying:
        return None
    scheme = qualifying[0]
    return _EVALUATORS[scheme.scheme_type](scheme, quantity)
