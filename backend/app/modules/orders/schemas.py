import uuid
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
