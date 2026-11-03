import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import CreditTransactionType
from app.database.base import (
    Base,
    created_at_column,
    in_values,
    updated_at_column,
    uuid_pk_column,
)

if TYPE_CHECKING:
    from app.models.retailer import Retailer


class CreditAccount(Base):
    """available_credit = credit_limit - current_outstanding (computed, not stored)."""

    __tablename__ = "credit_accounts"
    __table_args__ = (CheckConstraint("credit_limit >= 0", name="credit_limit_non_negative"),)

    id: Mapped[uuid.UUID] = uuid_pk_column()
    retailer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("retailers.id"), unique=True)
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    current_outstanding: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=0, server_default="0"
    )
    updated_at: Mapped[datetime] = updated_at_column()

    retailer: Mapped["Retailer"] = relationship(back_populates="credit_account")


class CreditLedger(Base):
    """Credit transactions. amount is signed: positive increases outstanding, negative reduces it."""

    __tablename__ = "credit_ledger"
    __table_args__ = (
        CheckConstraint(in_values("transaction_type", CreditTransactionType), name="type_valid"),
        CheckConstraint("amount <> 0", name="amount_non_zero"),
    )

    id: Mapped[uuid.UUID] = uuid_pk_column()
    retailer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("retailers.id"), index=True)
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id"))
    transaction_type: Mapped[str] = mapped_column(String(30))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at_column()
