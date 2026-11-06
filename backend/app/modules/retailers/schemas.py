import uuid
from decimal import Decimal

from pydantic import BaseModel


class SalesmanOut(BaseModel):
    name: str
    phone: str


class CreditOut(BaseModel):
    credit_limit: Decimal
    current_outstanding: Decimal  # confirmed orders not yet paid
    reserved_for_review: Decimal  # held by orders under review; released if they are rejected
    available_credit: Decimal  # credit_limit - current_outstanding - reserved_for_review


class PurchaseSummaryOut(BaseModel):
    total_orders: int
    confirmed_orders: int
    total_purchased: Decimal
    under_review_orders: int
    under_review_amount: Decimal
    rejected_orders: int


class RetailerProfileOut(BaseModel):
    id: uuid.UUID
    shop_name: str
    owner_name: str
    phone: str
    address: str
    city: str
    gstin: str | None
    assigned_salesman: SalesmanOut | None
    credit: CreditOut | None  # None: no credit account (no credit available)
    can_place_orders: bool  # False when no credit is available or ordering is paused
    ordering_restricted_reason: str | None = None  # set by the Admin to pause ordering
    purchases: PurchaseSummaryOut
