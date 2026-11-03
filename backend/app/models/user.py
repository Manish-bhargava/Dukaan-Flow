import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import UserRole
from app.database.base import Base, created_at_column, in_values, updated_at_column, uuid_pk_column

if TYPE_CHECKING:
    from app.models.retailer import Retailer


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(in_values("role", UserRole), name="role_valid"),
        # A retailer account must be linked to its retailer record.
        CheckConstraint("role <> 'RETAILER' OR retailer_id IS NOT NULL", name="retailer_link"),
    )

    id: Mapped[uuid.UUID] = uuid_pk_column()
    name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str] = mapped_column(String(15), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30), index=True)
    retailer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("retailers.id"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    retailer: Mapped["Retailer | None"] = relationship(
        back_populates="users", foreign_keys=[retailer_id]
    )


class OtpVerification(Base):
    __tablename__ = "otp_verifications"
    __table_args__ = (CheckConstraint("attempts >= 0", name="attempts_non_negative"),)

    id: Mapped[uuid.UUID] = uuid_pk_column()
    phone: Mapped[str] = mapped_column(String(15), index=True)
    otp_hash: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = created_at_column()
