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
    # Offline orders: the dealer price the device showed. Never used for pricing; if it
    # differs from the current price the order is held for Order Desk review.
    expected_unit_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    # Offline orders: the product's active scheme ids the device showed. If the product's
    # active schemes are different now, the order is held for review (never silently changed).
    expected_scheme_ids: list[uuid.UUID] | None = None


class CreateOrderInput(BaseModel):
    # Retailers order for their own shop (may be omitted); salesmen must name the retailer.
    retailer_id: uuid.UUID | None = None
    items: list[OrderItemInput] = Field(min_length=1)
    remarks: str | None = None
    # Device-generated unique id (salesman app): sending the same order again returns the
    # order already created instead of a duplicate.
    client_order_id: str | None = Field(default=None, min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    created_offline: bool = False  # created on the device without internet, synced later
    client_created_at: datetime | None = None  # when it was created on the device


class CorrectOrderItemInput(BaseModel):
    new_product_id: uuid.UUID | None = None
    new_quantity: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    unit: str | None = Field(default=None, max_length=30)
    # Why the desk changed the retailer's/salesman's request (kept in the order history).
    reason: str = Field(min_length=1, max_length=500)
    # Retailer wording to remember for the corrected product (retailer-specific alias).
    save_alias: str | None = Field(default=None, max_length=200)


class StatusReasonInput(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class RejectInput(BaseModel):
    # Optional: the Order Desk rejects with one click; a default reason is stored and shown.
    reason: str | None = Field(default=None, max_length=500)


class ApproveOrderInput(BaseModel):
    # Required only to release an order that exceeds the retailer's available credit.
    credit_override_reason: str | None = Field(default=None, max_length=500)
    # Confirm at the order's own prices although a price/scheme changed since it was placed.
    acknowledge_changes: bool = False


class ClarificationInput(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


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
    can_order: bool  # all lines in stock
    available_credit: Decimal  # credit_limit - current_outstanding
    within_credit: bool  # retailers cannot place the order when False
    ordering_restricted_reason: str | None = None  # set: the Admin paused ordering for this shop


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


class CreatorOut(BaseModel):
    id: uuid.UUID
    name: str
    role: str


class OrderSummaryOut(BaseModel):
    id: uuid.UUID
    order_number: str
    status: str
    source: str
    retailer: RetailerBriefOut
    item_count: int
    grand_total: Decimal
    created_at: datetime
    created_offline: bool
    client_order_id: str | None


class OrderOut(OrderTotalsOut):
    id: uuid.UUID
    order_number: str
    status: str
    source: str
    retailer: RetailerDetailOut
    remarks: str | None
    hold_reason: str | None
    rejection_reason: str | None
    clarification_message: str | None
    created_at: datetime
    approved_at: datetime | None
    approved_by: CreatorOut | None
    tally_exported_at: datetime | None
    created_by: CreatorOut  # who placed it (e.g. the salesman)
    created_offline: bool
    client_created_at: datetime | None
    client_order_id: str | None
    ai: AiSourceOut | None
    items: list[OrderItemOut]


class OrderPageOut(BaseModel):
    items: list[OrderSummaryOut]
    page: int
    limit: int
    total: int
