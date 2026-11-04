import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

Quantity = Field(gt=0, max_digits=12, decimal_places=3)


class OrderItemInput(BaseModel):
    product_id: uuid.UUID
    quantity: Decimal = Quantity
    # Must be stated explicitly and match the product's order unit (e.g. "case").
    unit: str = Field(min_length=1, max_length=30)


class CreateOrderInput(BaseModel):
    # Retailers order for their own shop (may be omitted); salesmen must name the retailer.
    retailer_id: uuid.UUID | None = None
    items: list[OrderItemInput] = Field(min_length=1)
    remarks: str | None = None


class CorrectOrderItemInput(BaseModel):
    new_product_id: uuid.UUID | None = None
    new_quantity: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    unit: str | None = Field(default=None, max_length=30)
    reason: str | None = None
    # Retailer wording to remember for the corrected product (retailer-specific alias).
    save_alias: str | None = Field(default=None, max_length=200)


class StatusReasonInput(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ApproveOrderInput(BaseModel):
    # Required only to release an order that exceeds the retailer's available credit.
    credit_override_reason: str | None = Field(default=None, max_length=500)


# ---------------------------------------------------------------- responses


class SchemeOut(BaseModel):
    scheme_type: str
    description: str
    min_quantity: Decimal
    free_quantity: Decimal
    discount_percentage: Decimal


class OrderTotalsOut(BaseModel):
    subtotal: Decimal
    discount_total: Decimal
    taxable_amount: Decimal
    gst_amount: Decimal
    grand_total: Decimal


class QuoteLineOut(BaseModel):
    product_id: uuid.UUID
    sku: str
    name: str
    pack_size: str
    order_unit: str
    quantity: Decimal  # paid cases
    free_quantity: Decimal
    price_basis: str
    unit_price: Decimal
    tax_inclusive: bool
    gst_rate: Decimal
    discount_percentage: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    gst_amount: Decimal
    line_total: Decimal
    scheme: SchemeOut | None
    available_stock: Decimal
    stock_ok: bool


class QuoteOut(BaseModel):
    lines: list[QuoteLineOut]
    totals: OrderTotalsOut
    can_order: bool


class RetailerBriefOut(BaseModel):
    id: uuid.UUID
    shop_name: str
    city: str


class RetailerDetailOut(RetailerBriefOut):
    owner_name: str
    phone: str
    address: str
    gstin: str | None


class CorrectionOut(BaseModel):
    old_product_id: uuid.UUID | None
    new_product_id: uuid.UUID
    old_quantity: Decimal
    new_quantity: Decimal
    reason: str | None
    created_at: datetime


class OrderItemOut(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    sku: str
    pack_size: str
    order_unit: str
    paid_quantity: Decimal
    free_quantity: Decimal
    price_basis: str
    unit_price: Decimal
    tax_inclusive: bool | None  # None: not recorded for lines created before it was stored
    discount_percentage: Decimal
    discount_amount: Decimal
    gst_rate: Decimal
    taxable_amount: Decimal
    gst_amount: Decimal
    line_total: Decimal
    scheme: SchemeOut | None
    corrections: list[CorrectionOut]


class AiSourceOut(BaseModel):
    extraction_id: uuid.UUID
    original_message: str


class OrderSummaryOut(BaseModel):
    id: uuid.UUID
    order_number: str
    status: str
    source: str
    retailer: RetailerBriefOut
    item_count: int
    grand_total: Decimal
    created_at: datetime


class OrderOut(OrderTotalsOut):
    id: uuid.UUID
    order_number: str
    status: str
    source: str
    retailer: RetailerDetailOut
    remarks: str | None
    hold_reason: str | None
    rejection_reason: str | None
    created_at: datetime
    approved_at: datetime | None
    ai: AiSourceOut | None
    items: list[OrderItemOut]


class OrderPageOut(BaseModel):
    items: list[OrderSummaryOut]
    page: int
    limit: int
    total: int
