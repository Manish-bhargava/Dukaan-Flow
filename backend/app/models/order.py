import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, false
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import OrderEventAction, OrderSource, OrderStatus, PriceBasis
from app.database.base import (
    Base,
    created_at_column,
    in_values,
    updated_at_column,
    uuid_pk_column,
)

if TYPE_CHECKING:
    from app.models.ai_order import AiExtraction
    from app.models.catalog import Product
    from app.models.retailer import Retailer
    from app.models.user import User

MONEY = Numeric(14, 2)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(in_values("source", OrderSource), name="source_valid"),
        CheckConstraint(in_values("status", OrderStatus), name="status_valid"),
        CheckConstraint(
            "subtotal >= 0 AND discount_total >= 0 AND taxable_amount >= 0"
            " AND gst_amount >= 0 AND grand_total >= 0",
            name="amounts_non_negative",
        ),
        Index("ix_orders_retailer_id_created_at", "retailer_id", "created_at"),
        Index("ix_orders_status_created_at", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk_column()
    order_number: Mapped[str] = mapped_column(String(50), unique=True)
    retailer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("retailers.id"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    ai_extraction_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_extractions.id"))
    source: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(
        String(30), default=OrderStatus.PENDING, server_default=OrderStatus.PENDING
    )
    subtotal: Mapped[Decimal] = mapped_column(MONEY, default=0, server_default="0")
    discount_total: Mapped[Decimal] = mapped_column(MONEY, default=0, server_default="0")
    taxable_amount: Mapped[Decimal] = mapped_column(MONEY, default=0, server_default="0")
    gst_amount: Mapped[Decimal] = mapped_column(MONEY, default=0, server_default="0")
    grand_total: Mapped[Decimal] = mapped_column(MONEY, default=0, server_default="0")
    remarks: Mapped[str | None] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    hold_reason: Mapped[str | None] = mapped_column(Text)
    # Set by the device that created the order (salesman app): unique, so a retried sync
    # returns the same order instead of creating a duplicate.
    client_order_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_offline: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    client_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clarification_message: Mapped[str | None] = mapped_column(Text)
    # Set when the order was included in a Tally export (exports are not repeated by accident).
    tally_exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    retailer: Mapped["Retailer"] = relationship()
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order")
    ai_extraction: Mapped["AiExtraction | None"] = relationship()
    creator: Mapped["User"] = relationship(foreign_keys=[created_by])
    approver: Mapped["User | None"] = relationship(foreign_keys=[approved_by])
    events: Mapped[list["OrderEvent"]] = relationship(back_populates="order", order_by="OrderEvent.created_at")


class OrderItem(Base):
    """One order line with immutable product, price, scheme and GST snapshots."""

    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("paid_quantity > 0", name="paid_quantity_positive"),
        CheckConstraint("free_quantity >= 0", name="free_quantity_non_negative"),
        CheckConstraint(in_values("price_basis", PriceBasis), name="price_basis_valid"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        CheckConstraint(
            "discount_percentage >= 0 AND discount_percentage <= 100", name="discount_range"
        ),
        CheckConstraint("gst_rate >= 0 AND gst_rate <= 100", name="gst_rate_range"),
        CheckConstraint(
            "discount_amount >= 0 AND taxable_amount >= 0 AND gst_amount >= 0 AND line_total >= 0",
            name="amounts_non_negative",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk_column()
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    product_name: Mapped[str] = mapped_column(String(200))
    sku: Mapped[str] = mapped_column(String(50))
    paid_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    free_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0, server_default="0")
    price_basis: Mapped[str] = mapped_column(String(20))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    discount_percentage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=0, server_default="0"
    )
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, server_default="0")
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    # Whether unit_price included GST. NULL only for lines created before this was recorded.
    tax_inclusive: Mapped[bool | None] = mapped_column(Boolean)
    # The scheme applied to this line and a snapshot of its terms at the time (NULL: none).
    scheme_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("schemes.id"))
    scheme_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    taxable_amount: Mapped[Decimal] = mapped_column(MONEY)
    gst_amount: Mapped[Decimal] = mapped_column(MONEY)
    line_total: Mapped[Decimal] = mapped_column(MONEY)

    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()
    corrections: Mapped[list["OrderCorrection"]] = relationship(back_populates="order_item")


class OrderCorrection(Base):
    __tablename__ = "order_corrections"
    __table_args__ = (
        CheckConstraint("old_quantity >= 0", name="old_quantity_non_negative"),
        CheckConstraint("new_quantity > 0", name="new_quantity_positive"),
    )

    id: Mapped[uuid.UUID] = uuid_pk_column()
    order_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("order_items.id"), index=True)
    old_product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id"))
    new_product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    old_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    new_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    corrected_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()

    order_item: Mapped[OrderItem] = relationship(back_populates="corrections")


class OrderEvent(Base):
    """Order history: who did what to an order, and when (received, confirmed, rejected,
    clarification requested, corrected, exported...). Append-only."""

    __tablename__ = "order_events"
    __table_args__ = (
        CheckConstraint(in_values("action", OrderEventAction), name="action_valid"),
        Index("ix_order_events_order_id_created_at", "order_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk_column()
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"))
    action: Mapped[str] = mapped_column(String(30))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))  # NULL: not recorded
    message: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_column()

    order: Mapped[Order] = relationship(back_populates="events")
    actor: Mapped["User | None"] = relationship()
