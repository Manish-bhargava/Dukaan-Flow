import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, created_at_column, updated_at_column, uuid_pk_column
from app.models.user import User


class AuditLog(Base):
    """Who changed what in the master data (retailers, products, prices, schemes, stock,
    credit, users, assignments, settings) and failed salesman syncs. Append-only.
    Order actions are in order_events."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk_column()
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(50))  # e.g. RETAILER_UPDATED, PRICE_CHANGED
    entity_type: Mapped[str] = mapped_column(String(30))  # retailer, product, price, scheme, stock, user...
    entity_id: Mapped[str | None] = mapped_column(String(64))
    entity_label: Mapped[str | None] = mapped_column(String(200))  # readable name at the time
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # e.g. {"before": {...}, "after": {...}}
    created_at: Mapped[datetime] = created_at_column()

    actor: Mapped[User | None] = relationship()


class AppSetting(Base):
    """Business settings, one row per key (see app/modules/settings)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = updated_at_column()


class SalesmanSyncStatus(Base):
    """What a salesman's phone last reported about its offline outbox. The outbox itself
    lives on the phone; the server only knows what the phone reports and what it synced."""

    __tablename__ = "salesman_sync_status"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # last data download
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pending_orders: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failed_orders: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    pending_visits: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
