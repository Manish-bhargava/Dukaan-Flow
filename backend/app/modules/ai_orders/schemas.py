import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.core.constants import AiInputType


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
    evidence: list[str] | None = None  # business evidence for the match (shown to people)
    clarification_reason: str | None = None
    requires_clarification: bool = False


class RecordExtractionInput(BaseModel):
    retailer_id: uuid.UUID | None = None
    original_message: str = Field(min_length=1)
    input_type: AiInputType = AiInputType.TEXT
    model_name: str | None = Field(default=None, max_length=100)
    raw_response: dict[str, Any] | None = None
    items: list[ExtractedItemInput]


class ConfirmedItemInput(BaseModel):
    """The user's reviewed choice for one extracted line."""

    # None for products the user added to the draft themselves.
    extraction_item_id: uuid.UUID | None = None
    product_id: uuid.UUID
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    unit: str = Field(min_length=1, max_length=30)


class ExtractOrderInput(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    retailer_id: uuid.UUID | None = None  # salesmen only; retailers capture for their own shop


class ConfirmExtractionInput(BaseModel):
    items: list[ConfirmedItemInput] = Field(min_length=1)
    remarks: str | None = None


# ---------------------------------------------------------------- responses


class ProductChoiceOut(BaseModel):
    product_id: uuid.UUID
    sku: str
    name: str
    pack_size: str
    order_unit: str


class ExtractionItemOut(BaseModel):
    id: uuid.UUID
    original_text: str
    extracted_name: str
    quantity: Decimal | None
    unit: str | None
    product: ProductChoiceOut | None  # the matched product (None: not recognised)
    confidence: Decimal
    alternatives: list[dict[str, Any]]
    requires_clarification: bool
    clarification: str | None  # why the user must check this line
    evidence: list[str]  # why this product was chosen (business evidence, not model reasoning)


class DraftSummaryOut(BaseModel):
    extraction_id: uuid.UUID
    created_at: datetime
    original_message: str
    item_count: int
    needs_clarification: bool  # some line needs the retailer's input before it can be placed


class ExtractionOut(BaseModel):
    extraction_id: uuid.UUID
    status: str
    input_type: str
    original_message: str
    model_name: str | None
    items: list[ExtractionItemOut]
