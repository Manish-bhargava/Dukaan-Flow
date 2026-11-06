import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import VisitOutcome
from app.database.base import Base, created_at_column, in_values


class ShopVisit(Base):
    """A salesman's visit to an assigned retailer. The id is generated on the device, so a
    visit recorded offline can be sent again safely (upsert by id)."""

    __tablename__ = "shop_visits"
    __table_args__ = (
        CheckConstraint(f"outcome IS NULL OR {in_values('outcome', VisitOutcome)}", name="outcome_valid"),
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="time_order"),
        Index("ix_shop_visits_salesman_id_started_at", "salesman_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    salesman_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    retailer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("retailers.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(String(20))  # ORDER_PLACED / NO_ORDER; NULL while open
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id"))
    created_at: Mapped[datetime] = created_at_column()
