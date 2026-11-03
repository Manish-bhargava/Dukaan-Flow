import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class ExtractedItemInput(BaseModel):
    """One line as produced by extraction + backend matching (Milestone 6 produces these)."""

    original_text: str = Field(min_length=1)
    extracted_name: str = Field(min_length=1, max_length=200)
    # None when the message does not state it; the item then requires clarification.
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    unit: str | None = Field(default=None, max_length=30)
    matched_product_id: uuid.UUID | None = None
    confidence: Decimal = Field(default=Decimal("0"), ge=0, le=1, max_digits=4, decimal_places=3)
    alternatives: list[dict[str, Any]] | None = None
    requires_clarification: bool = False


class RecordExtractionInput(BaseModel):
    retailer_id: uuid.UUID | None = None
    original_message: str = Field(min_length=1)
    model_name: str | None = Field(default=None, max_length=100)
    raw_response: dict[str, Any] | None = None
    items: list[ExtractedItemInput]


class ConfirmedItemInput(BaseModel):
    """The user's reviewed choice for one extracted line."""

    extraction_item_id: uuid.UUID
    product_id: uuid.UUID
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    unit: str = Field(min_length=1, max_length=30)


class ConfirmExtractionInput(BaseModel):
    items: list[ConfirmedItemInput] = Field(min_length=1)
    remarks: str | None = None
