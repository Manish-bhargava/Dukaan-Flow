import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import AiInputType, ExtractionStatus
from app.database.base import Base, created_at_column, in_values, uuid_pk_column

if TYPE_CHECKING:
    from app.models.retailer import Retailer


class RetailerAlias(Base):
    """A retailer's own wording for a product (e.g. "chhota biscuit"), used by AI matching."""

    __tablename__ = "retailer_aliases"
    __table_args__ = (UniqueConstraint("retailer_id", "normalized_alias"),)

    id: Mapped[uuid.UUID] = uuid_pk_column()
    retailer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("retailers.id"))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    alias: Mapped[str] = mapped_column(String(200))
    normalized_alias: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_at_column()

    retailer: Mapped["Retailer"] = relationship(back_populates="aliases")


class AiExtraction(Base):
    __tablename__ = "ai_extractions"
    __table_args__ = (
        CheckConstraint(in_values("extraction_status", ExtractionStatus), name="status_valid"),
        CheckConstraint(in_values("input_type", AiInputType), name="input_type_valid"),
    )

    id: Mapped[uuid.UUID] = uuid_pk_column()
    retailer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("retailers.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    original_message: Mapped[str] = mapped_column(Text)
    extraction_status: Mapped[str] = mapped_column(
        String(30), default=ExtractionStatus.PENDING, server_default=ExtractionStatus.PENDING
    )
    # How the order arrived; for VOICE original_message is the transcript, for IMAGE the
    # text the model read from the photo.
    input_type: Mapped[str] = mapped_column(String(10), default=AiInputType.TEXT, server_default=AiInputType.TEXT)
    model_name: Mapped[str | None] = mapped_column(String(100))
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_column()

    items: Mapped[list["AiExtractionItem"]] = relationship(
        back_populates="extraction", order_by="AiExtractionItem.line_no"
    )


class AiExtractionItem(Base):
    __tablename__ = "ai_extraction_items"
    __table_args__ = (
        CheckConstraint("quantity IS NULL OR quantity > 0", name="quantity_positive"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )

    id: Mapped[uuid.UUID] = uuid_pk_column()
    extraction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_extractions.id"), index=True)
    line_no: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # position in the message
    original_text: Mapped[str] = mapped_column(Text)
    extracted_name: Mapped[str] = mapped_column(String(200))
    # Quantity and unit stay NULL when the message does not state them; the item then
    # requires clarification instead of the system guessing (e.g. cases vs pieces).
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    unit: Mapped[str | None] = mapped_column(String(30))
    matched_product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id"))
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=0, server_default="0")
    alternatives: Mapped[list[Any] | None] = mapped_column(JSONB)
    # Business evidence for the match, e.g. ["Retailer used “chhota biscuit” for this 3 times"].
    evidence: Mapped[list[Any] | None] = mapped_column(JSONB)
    clarification_reason: Mapped[str | None] = mapped_column(Text)
    # The order line this AI line became (set when the draft is placed). Its current product
    # (after any Order Desk correction) is what the retailer meant: future matching learns from it.
    order_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("order_items.id"), index=True)
    requires_clarification: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    created_at: Mapped[datetime] = created_at_column()

    extraction: Mapped[AiExtraction] = relationship(back_populates="items")
