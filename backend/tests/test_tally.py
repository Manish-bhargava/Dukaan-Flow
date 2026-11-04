"""Tally CSV layout (pure)."""

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace as NS

from app.modules.exports import tally


def order(**item_overrides):
    item = NS(sku="SKU-BS-075", product_name="Glucose Biscuit 75g", paid_quantity=Decimal("25.000"),
              free_quantity=Decimal("2.000"), unit_price=Decimal("8.10"), price_basis="PIECE",
              tax_inclusive=False, discount_percentage=Decimal("0"), discount_amount=Decimal("0"),
              taxable_amount=Decimal("19440.00"), gst_rate=Decimal("5"), gst_amount=Decimal("972.00"),
              line_total=Decimal("20412.00"), scheme_snapshot={"description": "Buy 10 get 1 free"},
              product=NS(order_unit="case"))
    vars(item).update(item_overrides)
    retailer = NS(shop_name="=HYPERLINK(\"x\")", gstin=None, address="12, Main Rd\nNapier Town", city="Jabalpur",
                  phone="9000000101")
    return NS(order_number="DF-1", created_at=datetime(2026, 11, 3, 20, 0, tzinfo=UTC),
              approved_at=datetime(2026, 11, 4, 5, 0, tzinfo=UTC), retailer=retailer, items=[item],
              grand_total=Decimal("20412.00"))


def rows(*orders):
    return list(csv.DictReader(io.StringIO(tally.to_csv(orders))))


def test_row_values_and_ist_dates():
    [r] = rows(order())
    assert r["Voucher Date"] == "04-11-2026"  # 20:00 UTC on the 3rd is the 4th in IST
    assert (r["Billed Qty"], r["Free Qty"], r["Actual Qty"], r["Unit"]) == ("25", "2", "27", "case")
    assert (r["Rate"], r["Rate Per"], r["Rate Includes GST"]) == ("8.10", "piece", "No")
    assert (r["Taxable Value"], r["GST Rate %"], r["GST Amount"], r["Line Amount"]) == ("19440.00", "5.00", "972.00", "20412.00")
    assert r["Scheme"] == "Buy 10 get 1 free" and r["Party GSTIN"] == ""


def test_formulas_are_neutralised_and_newlines_flattened():
    [r] = rows(order())
    assert r["Party Name"].startswith("'=") and r["Party Address"] == "12, Main Rd Napier Town"


def test_unknown_gst_treatment_is_left_blank_not_guessed():
    [r] = rows(order(tax_inclusive=None, scheme_snapshot=None))
    assert r["Rate Includes GST"] == "" and r["Scheme"] == ""


def test_header_only_when_no_orders():
    assert tally.to_csv([]).strip() == ",".join(tally.COLUMNS)
