import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.constants import PriceBasis, SchemeType, UserRole

PHONE = r"^[6-9]\d{9}$"  # 10-digit Indian mobile number
Phone = Field(pattern=PHONE)
Money = Field(ge=0, max_digits=14, decimal_places=2)
Name = Field(min_length=1, max_length=150)
StaffRole = Literal[UserRole.SALESMAN, UserRole.ORDER_DESK, UserRole.ADMIN]


def _clean_email(value: str | None) -> str | None:
    value = (value or "").strip().lower()
    return value or None


# ---------------------------------------------------------------- shared outputs


class Ref(BaseModel):
    id: uuid.UUID
    name: str


class PageOut(BaseModel):
    items: list[Any]
    page: int
    limit: int
    total: int


# ---------------------------------------------------------------- retailers


class RetailerCreate(BaseModel):
    shop_name: str = Field(min_length=1, max_length=200)
    owner_name: str = Name
    phone: str = Phone  # also the retailer's login mobile (OTP)
    email: str | None = Field(default=None, max_length=255)  # where login OTPs are emailed
    address: str = Field(min_length=1, max_length=500)
    city: str = Field(min_length=1, max_length=100)
    gstin: str | None = Field(default=None, max_length=20)
    salesman_id: uuid.UUID | None = None
    credit_limit: Decimal = Money

    _email = field_validator("email")(_clean_email)


class RetailerUpdate(BaseModel):
    """Only the fields sent are changed (salesman_id: null unassigns)."""

    shop_name: str | None = Field(default=None, min_length=1, max_length=200)
    owner_name: str | None = Field(default=None, min_length=1, max_length=150)
    phone: str | None = Field(default=None, pattern=PHONE)
    email: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, min_length=1, max_length=500)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    gstin: str | None = Field(default=None, max_length=20)
    salesman_id: uuid.UUID | None = None
    is_active: bool | None = None

    _email = field_validator("email")(_clean_email)


class CreditUpdate(BaseModel):
    credit_limit: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    # True: pause new orders (reason required); False: allow ordering again.
    ordering_restricted: bool | None = None
    reason: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _check(self):
        if self.credit_limit is None and self.ordering_restricted is None:
            raise ValueError("Nothing to change")
        if self.ordering_restricted and not (self.reason or "").strip():
            raise ValueError("A reason is required to pause ordering")
        return self


class AssignmentInput(BaseModel):
    salesman_id: uuid.UUID | None  # None: remove the assignment
    retailer_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


# ---------------------------------------------------------------- users


class UserCreate(BaseModel):
    name: str = Name
    phone: str = Phone
    email: str | None = Field(default=None, max_length=255)
    role: StaffRole  # retailer logins are created with their retailer
    password: str = Field(min_length=8, max_length=128)

    _email = field_validator("email")(_clean_email)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    phone: str | None = Field(default=None, pattern=PHONE)
    email: str | None = Field(default=None, max_length=255)
    role: StaffRole | None = None
    is_active: bool | None = None

    _email = field_validator("email")(_clean_email)


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


# ---------------------------------------------------------------- catalogue


class NamedCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class NamedUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None


class PriceInput(BaseModel):
    dealer_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    price_basis: PriceBasis
    tax_inclusive: bool


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    name: str = Field(min_length=1, max_length=200)
    brand: str = Field(min_length=1, max_length=100)
    category_id: uuid.UUID
    pack_size: str = Field(min_length=1, max_length=100)
    units_per_case: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    base_unit: str = Field(default="piece", min_length=1, max_length=30)
    order_unit: str = Field(default="case", min_length=1, max_length=30)
    gst_rate: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)
    default_price: PriceInput | None = None
    opening_stock: Decimal = Field(default=Decimal(0), ge=0, max_digits=12, decimal_places=3)


class ProductUpdate(BaseModel):
    sku: str | None = Field(default=None, min_length=1, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    brand: str | None = Field(default=None, min_length=1, max_length=100)
    category_id: uuid.UUID | None = None
    pack_size: str | None = Field(default=None, min_length=1, max_length=100)
    units_per_case: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    base_unit: str | None = Field(default=None, min_length=1, max_length=30)
    order_unit: str | None = Field(default=None, min_length=1, max_length=30)
    gst_rate: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    is_active: bool | None = None


class PriceSet(PriceInput):
    product_id: uuid.UUID
    retailer_id: uuid.UUID | None = None  # None: the product's default price


class SchemeCreate(BaseModel):
    product_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)  # one scheme per product
    scheme_type: SchemeType
    min_quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    free_quantity: Decimal = Field(default=Decimal(0), ge=0, max_digits=12, decimal_places=3)
    discount_percentage: Decimal = Field(default=Decimal(0), ge=0, le=100, max_digits=5, decimal_places=2)
    starts_at: datetime
    ends_at: datetime | None = None

    @model_validator(mode="after")
    def _benefit(self):
        if self.scheme_type == SchemeType.FREE_GOODS and (self.free_quantity <= 0 or self.discount_percentage):
            raise ValueError("Buy X get Y needs a free quantity (and no discount)")
        if self.scheme_type == SchemeType.SLAB_DISCOUNT and (self.discount_percentage <= 0 or self.free_quantity):
            raise ValueError("A percentage discount needs a discount above 0 (and no free quantity)")
        if self.ends_at is not None and self.ends_at <= self.starts_at:
            raise ValueError("The end must be after the start")
        return self


class SchemeUpdate(BaseModel):
    min_quantity: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    free_quantity: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=3)
    discount_percentage: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    starts_at: datetime | None = None
    ends_at: datetime | None = None  # send null to make it open-ended
    is_active: bool | None = None


class StockAdjust(BaseModel):
    mode: Literal["add", "remove", "set"]  # add = restock, remove = damage/loss, set = stock count
    quantity: Decimal = Field(ge=0, max_digits=12, decimal_places=3)
    reason: str = Field(min_length=1, max_length=200)
