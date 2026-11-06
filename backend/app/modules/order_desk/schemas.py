import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.modules.orders.schemas import CreatorOut, OrderOut
from app.modules.retailers.schemas import CreditOut


class WarningOut(BaseModel):
    code: str  # INSUFFICIENT_STOCK, CREDIT_LIMIT_EXCEEDED, PRICE_CHANGED, SCHEME_CHANGED, ...
    severity: str  # error | warning
    message: str


class PersonOut(BaseModel):
    id: uuid.UUID
    name: str
    phone: str


class EventOut(BaseModel):
    action: str
    actor: CreatorOut | None  # None: not recorded (history backfilled for older orders)
    message: str | None
    details: dict[str, Any] | None
    created_at: datetime


class DeskRetailerOut(BaseModel):
    id: uuid.UUID
    shop_name: str
    owner_name: str
    phone: str
    city: str


class DeskOrderRowOut(BaseModel):
    id: uuid.UUID
    order_number: str
    status: str
    source: str
    retailer: DeskRetailerOut
    salesman: PersonOut | None
    created_by: CreatorOut
    item_count: int
    grand_total: Decimal
    created_at: datetime
    approved_at: datetime | None
    approved_by: CreatorOut | None
    created_offline: bool
    tally_exported_at: datetime | None
    reason: str | None  # rejection reason / clarification message / hold reason
    warnings: list[WarningOut]
    last_action: EventOut | None


class DeskOrderPageOut(BaseModel):
    items: list[DeskOrderRowOut]
    page: int
    limit: int
    total: int


class LineStockOut(BaseModel):
    item_id: uuid.UUID
    needed: Decimal  # paid + free cases of this product on the order
    available: Decimal  # current stock in cases
    ok: bool


class AiProductOut(BaseModel):
    id: uuid.UUID
    sku: str
    name: str
    pack_size: str


class AiLineOut(BaseModel):
    """How the AI read one line of the retailer's message (before the retailer confirmed it)."""

    original_text: str
    extracted_name: str
    quantity: Decimal | None
    unit: str | None
    product: AiProductOut | None  # the AI's recommended product
    confidence: Decimal
    requires_clarification: bool
    clarification_reason: str | None
    evidence: list[str]
    alternatives: list[dict[str, Any]]


class OrderReviewOut(BaseModel):
    order: OrderOut
    salesman: PersonOut | None
    credit: CreditOut | None
    stock: list[LineStockOut]
    warnings: list[WarningOut]
    ai_input_type: str | None  # TEXT / IMAGE / VOICE for AI orders
    ai_lines: list[AiLineOut]
    history: list[EventOut]


class OverviewOut(BaseModel):
    received_today: int
    pending_review: int
    awaiting_clarification: int
    confirmed_today: int
    confirmed_total: int
    rejected_today: int
    rejected_total: int
    with_stock_or_credit_issues: int
    not_exported: int


class ProductTotalOut(BaseModel):
    product_id: uuid.UUID
    sku: str
    name: str
    pack_size: str
    order_unit: str
    paid: Decimal
    free: Decimal
    total: Decimal
    orders: int


class StopOrderOut(BaseModel):
    order_id: uuid.UUID
    order_number: str
    grand_total: Decimal
    approved_at: datetime | None


class StopOut(BaseModel):
    """One shop: all its confirmed orders in the period, quantities combined."""

    retailer_id: uuid.UUID
    shop_name: str
    owner_name: str
    phone: str
    address: str
    city: str
    grand_total: Decimal
    orders: list[StopOrderOut]
    products: list[ProductTotalOut]


class BeatOut(BaseModel):
    salesman: PersonOut | None  # None: shops without a salesman
    stops: list[StopOut]
    products: list[ProductTotalOut]
    orders_count: int
    grand_total: Decimal


class DispatchOut(BaseModel):
    order_count: int
    grand_total: Decimal
    products: list[ProductTotalOut]
    beats: list[BeatOut]
