import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Numeric, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, created_at_column, updated_at_column, uuid_pk_column

if TYPE_CHECKING:
    from app.models.inventory import Inventory
    from app.models.pricing import RetailerPrice, Scheme


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = uuid_pk_column()
    name: Mapped[str] = mapped_column(String(100), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())

    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("units_per_case > 0", name="units_per_case_positive"),
        CheckConstraint("gst_rate >= 0 AND gst_rate <= 100", name="gst_rate_range"),
    )

    id: Mapped[uuid.UUID] = uuid_pk_column()
    sku: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    brand: Mapped[str] = mapped_column(String(100))
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"), index=True)
    pack_size: Mapped[str] = mapped_column(String(100))
    units_per_case: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    base_unit: Mapped[str] = mapped_column(String(30))
    order_unit: Mapped[str] = mapped_column(String(30))
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    image_url: Mapped[str | None] = mapped_column(Text)  # original Cloudinary secure_url
    image_public_id: Mapped[str | None] = mapped_column(String(255))  # Cloudinary public_id
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    category: Mapped[Category] = relationship(back_populates="products")
    inventory: Mapped["Inventory | None"] = relationship(back_populates="product")
    schemes: Mapped[list["Scheme"]] = relationship(back_populates="product")
    retailer_prices: Mapped[list["RetailerPrice"]] = relationship(back_populates="product")
