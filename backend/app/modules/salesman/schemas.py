import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.constants import VisitOutcome
from app.modules.products.schemas import CategoryOut, PriceOut, SchemeOut
from app.modules.retailers.schemas import CreditOut


class RecentOrderOut(BaseModel):
    id: uuid.UUID
    order_number: str
    created_at: datetime
    grand_total: Decimal
    status: str
    item_count: int


class AssignedRetailerOut(BaseModel):
    id: uuid.UUID
    shop_name: str
    owner_name: str
    phone: str
    address: str
    city: str
    gstin: str | None
    registered_mobiles: list[str]  # login mobile(s) of the retailer's account (users.phone)
    last_order_at: datetime | None
    credit: CreditOut | None
    recent_orders: list[RecentOrderOut]
    ordering_restricted_reason: str | None = None  # Admin paused ordering for this shop


class BundleProductOut(BaseModel):
    """Product facts shared by all retailers; prices are per retailer in `prices`."""

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
    image_url: str | None
    thumbnail_url: str | None
    stock_cases: Decimal
    in_stock: bool
    schemes: list[SchemeOut]


class SyncBundleOut(BaseModel):
    synced_at: datetime
    retailers: list[AssignedRetailerOut]
    categories: list[CategoryOut]
    products: list[BundleProductOut]
    # retailer_id -> product_id -> that retailer's current price
    prices: dict[str, dict[str, PriceOut]]


class TodayVisitOut(BaseModel):
    id: uuid.UUID
    retailer_id: uuid.UUID
    shop_name: str
    started_at: datetime
    ended_at: datetime | None
    outcome: str | None


class SalesmanHomeOut(BaseModel):
    """Today's work as recorded on the server (IST day)."""

    date: str
    assigned_retailers: int
    visits_today: int
    orders_today: int
    todays_visits: list[TodayVisitOut]


class VisitInput(BaseModel):
    id: uuid.UUID  # generated on the device; sending the same visit again updates it
    retailer_id: uuid.UUID
    started_at: datetime
    ended_at: datetime | None = None
    outcome: VisitOutcome | None = None
    client_order_id: str | None = Field(default=None, max_length=64)  # the order placed during the visit


class VisitOut(BaseModel):
    id: uuid.UUID
    retailer_id: uuid.UUID
    started_at: datetime
    ended_at: datetime | None
    outcome: str | None
    order_id: uuid.UUID | None


class SyncStatusInput(BaseModel):
    """What the phone's outbox holds after a sync run (reported for the Admin)."""

    pending_orders: int = Field(ge=0, le=10000)
    failed_orders: int = Field(ge=0, le=10000)
    pending_visits: int = Field(ge=0, le=10000)
    last_error: str | None = Field(default=None, max_length=500)
