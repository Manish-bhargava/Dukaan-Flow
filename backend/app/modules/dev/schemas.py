import uuid
from datetime import datetime
from decimal import Decimal

from typing import Any

from pydantic import BaseModel, ConfigDict


class DbStatusOut(BaseModel):
    status: str
    database: str
    server_version: str
    migration_revision: str | None
    latency_ms: float


class SeedSummaryOut(BaseModel):
    users: int
    users_by_role: dict[str, int]
    retailers: int
    categories: int
    products: int
    retailer_prices: int
    schemes: int
    inventory_records: int
    retailer_aliases: int
    credit_accounts: int
    credit_ledger: int
    stock_movements: int
    orders: int
    orders_by_status: dict[str, int]
    order_items: int
    order_corrections: int
    ai_extractions: int
    ai_extraction_items: int
    otp_verifications: int


class ProductOut(BaseModel):
    id: uuid.UUID
    sku: str
    name: str
    brand: str
    category: str
    pack_size: str
    units_per_case: Decimal
    base_unit: str
    order_unit: str
    gst_rate: Decimal
    is_active: bool
    stock_cases: Decimal | None


class SalesmanOut(BaseModel):
    id: uuid.UUID
    name: str
    phone: str


class CreditOut(BaseModel):
    credit_limit: Decimal
    current_outstanding: Decimal
    available_credit: Decimal


class RetailerOut(BaseModel):
    id: uuid.UUID
    shop_name: str
    owner_name: str
    phone: str
    address: str
    city: str
    gstin: str | None
    is_active: bool
    assigned_salesman: SalesmanOut | None
    credit: CreditOut | None


class RetailerPriceOut(BaseModel):
    dealer_price: Decimal
    price_basis: str
    tax_inclusive: bool
    effective_from: datetime
    effective_to: datetime | None


class SchemeOut(BaseModel):
    id: uuid.UUID
    scheme_type: str
    min_quantity: Decimal
    free_quantity: Decimal | None
    discount_percentage: Decimal | None
    starts_at: datetime
    ends_at: datetime | None


class RetailerProductOut(ProductOut):
    price: RetailerPriceOut | None
    schemes: list[SchemeOut]


class RetailerRef(BaseModel):
    id: uuid.UUID
    shop_name: str


class RetailerProductsOut(BaseModel):
    retailer: RetailerRef
    products: list[RetailerProductOut]


class ORMOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(ORMOut):
    id: uuid.UUID
    name: str
    phone: str
    email: str | None
    role: str
    retailer_id: uuid.UUID | None
    is_active: bool


class OrderSummaryOut(BaseModel):
    id: uuid.UUID
    order_number: str
    retailer_id: uuid.UUID
    shop_name: str
    source: str
    status: str
    item_count: int
    subtotal: Decimal
    discount_total: Decimal
    taxable_amount: Decimal
    gst_amount: Decimal
    grand_total: Decimal
    created_at: datetime
    approved_at: datetime | None


class OrderItemOut(ORMOut):
    id: uuid.UUID
    product_id: uuid.UUID
    sku: str
    product_name: str
    paid_quantity: Decimal
    free_quantity: Decimal
    price_basis: str
    unit_price: Decimal
    discount_percentage: Decimal
    discount_amount: Decimal
    gst_rate: Decimal
    taxable_amount: Decimal
    gst_amount: Decimal
    line_total: Decimal


class CorrectionOut(ORMOut):
    id: uuid.UUID
    order_item_id: uuid.UUID
    old_product_id: uuid.UUID | None
    new_product_id: uuid.UUID
    old_quantity: Decimal
    new_quantity: Decimal
    corrected_by: uuid.UUID
    reason: str | None
    created_at: datetime


class StockMovementOut(ORMOut):
    id: uuid.UUID
    product_id: uuid.UUID
    order_id: uuid.UUID | None
    movement_type: str
    quantity: Decimal
    reference: str | None
    created_by: uuid.UUID
    created_at: datetime


class LedgerEntryOut(ORMOut):
    id: uuid.UUID
    retailer_id: uuid.UUID
    order_id: uuid.UUID | None
    transaction_type: str
    amount: Decimal
    description: str | None
    created_by: uuid.UUID
    created_at: datetime


class OrderDetailOut(OrderSummaryOut):
    created_by: uuid.UUID
    ai_extraction_id: uuid.UUID | None
    remarks: str | None
    rejection_reason: str | None
    approved_by: uuid.UUID | None
    items: list[OrderItemOut]
    corrections: list[CorrectionOut]
    stock_movements: list[StockMovementOut]
    ledger_entries: list[LedgerEntryOut]


class ExtractionItemOut(ORMOut):
    id: uuid.UUID
    original_text: str
    extracted_name: str
    quantity: Decimal | None
    unit: str | None
    matched_product_id: uuid.UUID | None
    confidence: Decimal
    alternatives: list[Any] | None
    requires_clarification: bool


class ExtractionOut(BaseModel):
    id: uuid.UUID
    retailer_id: uuid.UUID
    user_id: uuid.UUID
    original_message: str
    extraction_status: str
    model_name: str | None
    created_at: datetime
    order_number: str | None
    items: list[ExtractionItemOut]


class InventoryOut(BaseModel):
    product_id: uuid.UUID
    sku: str
    name: str
    stock_cases: Decimal
    movements: list[StockMovementOut]


class CreditDetailOut(BaseModel):
    retailer_id: uuid.UUID
    shop_name: str
    credit_limit: Decimal
    current_outstanding: Decimal
    available_credit: Decimal
    ledger: list[LedgerEntryOut]


class IntegrityCheckOut(BaseModel):
    name: str
    passed: bool
    problems: list[str]


class IntegrityOut(BaseModel):
    all_passed: bool
    checks: list[IntegrityCheckOut]
