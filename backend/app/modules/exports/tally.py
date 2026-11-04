"""Tally CSV layout for confirmed (APPROVED) orders: one row per order line.

Only values DukaanFlow actually stores are exported, all taken from the order's snapshots.
GST is exported as rate + amount; it is not split into CGST/SGST/IGST because place of
supply is not recorded. A line whose GST treatment was not recorded gets an empty
"Rate Includes GST" cell rather than a guess. Change the columns here to adjust the format.
"""

import csv
import io
from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.models import Order, OrderItem

IST = ZoneInfo("Asia/Kolkata")

COLUMNS = [
    "Voucher Date", "Voucher Number", "Confirmed On", "Party Name", "Party GSTIN", "Party Address",
    "Party City", "Party Phone", "SKU", "Item Name", "Billed Qty", "Free Qty", "Actual Qty", "Unit",
    "Rate", "Rate Per", "Rate Includes GST", "Discount %", "Discount Amount", "Taxable Value",
    "GST Rate %", "GST Amount", "Line Amount", "Scheme", "Order Total",
]


def _date(value: datetime | None) -> str:
    return value.astimezone(IST).strftime("%d-%m-%Y") if value else ""


def _qty(value: Decimal) -> str:
    return f"{value.normalize():f}"


def _text(value: str | None) -> str:
    """Neutralise spreadsheet formulas in free text (CSV injection)."""
    value = (value or "").replace("\r", " ").replace("\n", " ").strip()
    return f"'{value}" if value[:1] in ("=", "+", "-", "@", "\t") else value


def _tax_inclusive(item: OrderItem) -> str:
    return "" if item.tax_inclusive is None else ("Yes" if item.tax_inclusive else "No")


def row(order: Order, item: OrderItem) -> list[str]:
    r = order.retailer
    unit = item.product.order_unit
    return [
        _date(order.created_at), order.order_number, _date(order.approved_at), _text(r.shop_name),
        _text(r.gstin), _text(r.address), _text(r.city), _text(r.phone), item.sku, _text(item.product_name),
        _qty(item.paid_quantity), _qty(item.free_quantity), _qty(item.paid_quantity + item.free_quantity), unit,
        f"{item.unit_price:.2f}", item.price_basis.lower(), _tax_inclusive(item),
        f"{item.discount_percentage:.2f}", f"{item.discount_amount:.2f}", f"{item.taxable_amount:.2f}",
        f"{item.gst_rate:.2f}", f"{item.gst_amount:.2f}", f"{item.line_total:.2f}",
        _text((item.scheme_snapshot or {}).get("description")), f"{order.grand_total:.2f}",
    ]


def to_csv(orders: Iterable[Order]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for order in orders:
        for item in order.items:
            writer.writerow(row(order, item))
    return buffer.getvalue()
