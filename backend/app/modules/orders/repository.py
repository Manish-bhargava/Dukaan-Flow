import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Order, Product


def get_order(db: Session, order_id: uuid.UUID, lock: bool = False) -> Order | None:
    statement = select(Order).where(Order.id == order_id).options(selectinload(Order.items))
    if lock:
        statement = statement.with_for_update(of=Order).execution_options(populate_existing=True)
    return db.scalar(statement)


def list_orders(
    db: Session, retailer_ids: list[uuid.UUID] | None, status: str | None = None
) -> list[Order]:
    statement = select(Order).options(selectinload(Order.items)).order_by(Order.created_at.desc())
    if retailer_ids is not None:
        statement = statement.where(Order.retailer_id.in_(retailer_ids))
    if status is not None:
        statement = statement.where(Order.status == status)
    return list(db.scalars(statement))


def get_products(db: Session, product_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Product]:
    statement = select(Product).where(Product.id.in_(list(product_ids)))
    return {product.id: product for product in db.scalars(statement)}
