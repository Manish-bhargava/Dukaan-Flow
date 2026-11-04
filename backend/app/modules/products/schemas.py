import uuid
from decimal import Decimal

from pydantic import BaseModel


class CategoryOut(BaseModel):
    id: uuid.UUID
    name: str


class PriceOut(BaseModel):
    dealer_price: Decimal
    price_basis: str  # PIECE or CASE
    tax_inclusive: bool
    case_price: Decimal  # dealer price for one order unit (case), before GST and schemes


class SchemeOut(BaseModel):
    id: uuid.UUID
    scheme_type: str
    description: str  # e.g. "Buy 10 get 1 free"
    min_quantity: Decimal
    free_quantity: Decimal
    discount_percentage: Decimal


class ProductOut(BaseModel):
    id: uuid.UUID
    sku: str
    name: str
    brand: str
    category: CategoryOut
    pack_size: str
    units_per_case: Decimal
    base_unit: str
    order_unit: str
    gst_rate: Decimal
    image_url: str | None  # optimized delivery URL (800px, auto format/quality); None: no image
    thumbnail_url: str | None  # same image at 400px for lists
    price: PriceOut
    stock_cases: Decimal
    in_stock: bool
    schemes: list[SchemeOut]


class ProductPageOut(BaseModel):
    items: list[ProductOut]
    page: int
    limit: int
    total: int


class ProductImageOut(BaseModel):
    product_id: uuid.UUID
    image_public_id: str
    image_url: str
    thumbnail_url: str
