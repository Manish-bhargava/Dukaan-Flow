"""Pricing engine: retailer price + scheme + GST for one order line, and order totals.

Rules (V1):
- Quantities are in the product's order unit (cases). A PIECE price is converted to a
  case price with units_per_case; a CASE price is used as is.
- Which scheme applies, and its free quantity or discount, comes from the scheme engine
  (app/modules/schemes/engine.py); this module only turns that into money.
- tax_inclusive=False: GST is added on top of the discounted amount.
  tax_inclusive=True: GST is extracted from the discounted amount.
- Money is rounded to 2 decimals (half up) per line; order totals are sums of line values.
  subtotal = sum of (taxable_amount + discount_amount), i.e. value before discount, excluding GST,
  so subtotal - discount_total = taxable_amount and taxable_amount + gst_amount = grand_total.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.constants import ErrorCode, PriceBasis
from app.core.permissions import ensure_can_access_retailer
from app.exceptions.base import AppException
from app.models import Product, Retailer, RetailerPrice, User
from app.modules.pricing import repository
from app.modules.schemes import engine as schemes_engine
from app.modules.schemes.engine import SchemeBenefit, SchemeLike

HUNDRED = Decimal("100")


@dataclass(frozen=True)
class LineAmounts:
    paid_quantity: Decimal
    free_quantity: Decimal
    price_basis: str
    unit_price: Decimal  # the retailer's dealer_price snapshot, per price_basis
    tax_inclusive: bool  # whether unit_price already includes GST
    gross_amount: Decimal  # before discount
    discount_percentage: Decimal
    discount_amount: Decimal
    gst_rate: Decimal
    taxable_amount: Decimal
    gst_amount: Decimal
    line_total: Decimal
    scheme: SchemeBenefit | None

    @property
    def scheme_id(self) -> uuid.UUID | None:
        return self.scheme.scheme_id if self.scheme else None


@dataclass(frozen=True)
class OrderTotals:
    subtotal: Decimal
    discount_total: Decimal
    taxable_amount: Decimal
    gst_amount: Decimal
    grand_total: Decimal


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_line(
    *,
    quantity: Decimal,
    dealer_price: Decimal,
    price_basis: str,
    tax_inclusive: bool,
    units_per_case: Decimal,
    gst_rate: Decimal,
    schemes: Sequence[SchemeLike],
) -> LineAmounts:
    if quantity <= 0:
        raise AppException("Quantity must be greater than zero", ErrorCode.VALIDATION_ERROR, 422)

    scheme = schemes_engine.evaluate(quantity, schemes)
    free_quantity = scheme.free_quantity if scheme else Decimal("0")
    discount_percentage = scheme.discount_percentage if scheme else Decimal("0")

    case_price = dealer_price * units_per_case if price_basis == PriceBasis.PIECE else dealer_price
    gross_amount = money(quantity * case_price)
    discount_amount = money(gross_amount * discount_percentage / HUNDRED)
    net_amount = gross_amount - discount_amount

    if tax_inclusive:
        taxable_amount = money(net_amount * HUNDRED / (HUNDRED + gst_rate))
        gst_amount = net_amount - taxable_amount
    else:
        taxable_amount = net_amount
        gst_amount = money(taxable_amount * gst_rate / HUNDRED)

    return LineAmounts(
        paid_quantity=quantity,
        free_quantity=free_quantity,
        price_basis=price_basis,
        unit_price=dealer_price,
        tax_inclusive=tax_inclusive,
        gross_amount=gross_amount,
        discount_percentage=discount_percentage,
        discount_amount=discount_amount,
        gst_rate=gst_rate,
        taxable_amount=taxable_amount,
        gst_amount=gst_amount,
        line_total=taxable_amount + gst_amount,
        scheme=scheme,
    )


class LineSnapshot(Protocol):
    discount_amount: Decimal
    taxable_amount: Decimal
    gst_amount: Decimal
    line_total: Decimal


def calculate_totals(lines: Sequence[LineSnapshot]) -> OrderTotals:
    return OrderTotals(
        subtotal=sum((line.taxable_amount + line.discount_amount for line in lines), Decimal("0")),
        discount_total=sum((line.discount_amount for line in lines), Decimal("0")),
        taxable_amount=sum((line.taxable_amount for line in lines), Decimal("0")),
        gst_amount=sum((line.gst_amount for line in lines), Decimal("0")),
        grand_total=sum((line.line_total for line in lines), Decimal("0")),
    )


def price_lines(
    db: Session,
    retailer_id: uuid.UUID,
    items: Sequence[tuple[Product, Decimal]],
    at: datetime,
) -> list[LineAmounts]:
    """Price (product, quantity-in-cases) pairs for a retailer at a point in time."""
    product_ids = [product.id for product, _ in items]
    prices = repository.get_effective_prices(db, retailer_id, at, product_ids)
    schemes = repository.get_active_schemes(db, at, product_ids)

    lines = []
    for product, quantity in items:
        price = prices.get(product.id)
        if price is None:
            raise AppException(
                f"No price is configured for {product.sku} for this retailer",
                ErrorCode.PRICE_NOT_AVAILABLE,
                status_code=409,
                details={"sku": product.sku},
            )
        lines.append(
            calculate_line(
                quantity=quantity,
                dealer_price=price.dealer_price,
                price_basis=price.price_basis,
                tax_inclusive=price.tax_inclusive,
                units_per_case=product.units_per_case,
                gst_rate=product.gst_rate,
                schemes=schemes_engine.active_schemes(schemes.get(product.id, []), at),
            )
        )
    return lines


def get_retailer_prices(
    db: Session, actor: User, retailer: Retailer, at: datetime
) -> dict[uuid.UUID, RetailerPrice]:
    """A retailer's current price list; only users allowed to see that retailer's data."""
    ensure_can_access_retailer(actor, retailer)
    return repository.get_effective_prices(db, retailer.id, at)
