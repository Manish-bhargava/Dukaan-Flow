import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import PriceBasis, SchemeType
from app.database.base import Base, created_at_column, in_values, uuid_pk_column

if TYPE_CHECKING:
    from app.models.catalog import Product
    from app.models.retailer import Retailer


class RetailerPrice(Base):
    """A dealer price for a product, valid from effective_from until effective_to.
    retailer_id NULL is the product's default price, used for retailers without their own
    price. Changes close the current row and add a new one, so rows are the price history."""

    __tablename__ = "retailer_prices"
    __table_args__ = (
        CheckConstraint("dealer_price >= 0", name="dealer_price_non_negative"),
        CheckConstraint(in_values("price_basis", PriceBasis), name="price_basis_valid"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from", name="effective_range"
        ),
        Index("ix_retailer_prices_retailer_id_product_id", "retailer_id", "product_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk_column()
    retailer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("retailers.id"))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    dealer_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    price_basis: Mapped[str] = mapped_column(String(20))
    # No default on purpose: GST inclusion must be stated explicitly for every price.
    tax_inclusive: Mapped[bool] = mapped_column(Boolean)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))  # NULL: seed/import
    created_at: Mapped[datetime] = created_at_column()

    retailer: Mapped["Retailer | None"] = relationship(back_populates="prices")
    product: Mapped["Product"] = relationship(back_populates="retailer_prices")


class Scheme(Base):
    """FREE_GOODS uses free_quantity; SLAB_DISCOUNT uses discount_percentage. The unused one is 0."""

    __tablename__ = "schemes"
    __table_args__ = (
        CheckConstraint(in_values("scheme_type", SchemeType), name="scheme_type_valid"),
        CheckConstraint("min_quantity > 0", name="min_quantity_positive"),
        CheckConstraint(
            "(scheme_type = 'FREE_GOODS' AND free_quantity > 0 AND discount_percentage = 0)"
            " OR (scheme_type = 'SLAB_DISCOUNT' AND discount_percentage > 0"
            " AND discount_percentage <= 100 AND free_quantity = 0)",
            name="benefit_matches_type",
        ),
        CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="date_range"),
        Index("ix_schemes_product_id_is_active", "product_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = uuid_pk_column()
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    scheme_type: Mapped[str] = mapped_column(String(30))
    min_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    free_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0, server_default="0")
    discount_percentage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=0, server_default="0"
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = created_at_column()

    product: Mapped["Product"] = relationship(back_populates="schemes")
