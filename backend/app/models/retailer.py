import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, created_at_column, uuid_pk_column

if TYPE_CHECKING:
    from app.models.ai_order import RetailerAlias
    from app.models.credit import CreditAccount
    from app.models.pricing import RetailerPrice
    from app.models.user import User


class Retailer(Base):
    __tablename__ = "retailers"

    id: Mapped[uuid.UUID] = uuid_pk_column()
    shop_name: Mapped[str] = mapped_column(String(200))
    owner_name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str] = mapped_column(String(15))
    address: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(String(100))
    gstin: Mapped[str | None] = mapped_column(String(20))
    # users.retailer_id and retailers.assigned_salesman_id reference each other;
    # use_alter adds this FK after both tables exist.
    assigned_salesman_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", use_alter=True), index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = created_at_column()

    users: Mapped[list["User"]] = relationship(
        back_populates="retailer", foreign_keys="User.retailer_id"
    )
    assigned_salesman: Mapped["User | None"] = relationship(foreign_keys=[assigned_salesman_id])
    credit_account: Mapped["CreditAccount | None"] = relationship(back_populates="retailer")
    prices: Mapped[list["RetailerPrice"]] = relationship(back_populates="retailer")
    aliases: Mapped[list["RetailerAlias"]] = relationship(back_populates="retailer")
