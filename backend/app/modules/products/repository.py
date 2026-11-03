import uuid
from collections.abc import Collection

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import Category, Inventory, Product


def list_active_categories(db: Session) -> list[Category]:
    return list(db.scalars(select(Category).where(Category.is_active.is_(True)).order_by(Category.name)))


def list_products(
    db: Session,
    product_ids: Collection[uuid.UUID],
    search: str | None,
    category_id: uuid.UUID | None,
    offset: int,
    limit: int,
) -> tuple[list[Product], int]:
    """Active products (in active categories) among `product_ids`, with total count."""
    statement = (
        select(Product)
        .join(Product.category)
        .where(Product.id.in_(list(product_ids)), Product.is_active.is_(True), Category.is_active.is_(True))
    )
    if category_id is not None:
        statement = statement.where(Product.category_id == category_id)
    if search:
        pattern = f"%{search}%"
        statement = statement.where(
            or_(Product.name.ilike(pattern), Product.brand.ilike(pattern), Product.sku.ilike(pattern))
        )
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    page = db.scalars(
        statement.options(joinedload(Product.category))
        .order_by(Category.name, Product.name, Product.units_per_case.desc(), Product.sku)
        .offset(offset)
        .limit(limit)
    )
    return list(page), total or 0


def get_stock(db: Session, product_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, object]:
    statement = select(Inventory.product_id, Inventory.stock_cases).where(
        Inventory.product_id.in_(list(product_ids))
    )
    return dict(db.execute(statement).tuples().all())
