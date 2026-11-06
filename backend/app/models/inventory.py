import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import StockMovementType
from app.database.base import (
    Base,
    created_at_column,
    in_values,
    updated_at_column,
    uuid_pk_column,
)

if TYPE_CHECKING:
    from app.models.catalog import Product


class Inventory(Base):
    """Current stock per product (single warehouse in V1)."""

    __tablename__ = "inventory"
    __table_args__ = (CheckConstraint("stock_cases >= 0", name="stock_non_negative"),)

    id: Mapped[uuid.UUID] = uuid_pk_column()
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), unique=True)
    stock_cases: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0, server_default="0")
    updated_at: Mapped[datetime] = updated_at_column()

    product: Mapped["Product"] = relationship(back_populates="inventory")


class StockMovement(Base):
    """Audit trail of stock changes. quantity is signed: positive adds stock, negative removes it."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint(in_values("movement_type", StockMovementType), name="type_valid"),
        CheckConstraint("quantity <> 0", name="quantity_non_zero"),
    )

    id: Mapped[uuid.UUID] = uuid_pk_column()
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id"))
    movement_type: Mapped[str] = mapped_column(String(30))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    reference: Mapped[str | None] = mapped_column(String(200))
    stock_after: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))  # stock once applied (before = after - quantity)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at_column()
