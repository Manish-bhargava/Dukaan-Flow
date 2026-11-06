import uuid
from collections.abc import Iterable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Order, Product, Retailer


def get_order(db: Session, order_id: uuid.UUID, lock: bool = False) -> Order | None:
    statement = select(Order).where(Order.id == order_id).options(selectinload(Order.items))
    if lock:
        statement = statement.with_for_update(of=Order).execution_options(populate_existing=True)
    return db.scalar(statement)


def get_order_by_client_id(db: Session, client_order_id: str) -> Order | None:
    statement = select(Order).where(Order.client_order_id == client_order_id).options(selectinload(Order.items))
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


def search_orders(
    db: Session,
    retailer_ids: list[uuid.UUID] | None,
    statuses: list[str],
    source: str | None,
    search: str | None,
    offset: int,
    limit: int,
    created_by: uuid.UUID | None = None,
    retailer_id: uuid.UUID | None = None,
) -> tuple[list[Order], int]:
    statement = select(Order).join(Order.retailer)
    if created_by is not None:
        statement = statement.where(Order.created_by == created_by)
    if retailer_id is not None:
        statement = statement.where(Order.retailer_id == retailer_id)
    if retailer_ids is not None:
        statement = statement.where(Order.retailer_id.in_(retailer_ids))
    if statuses:
        statement = statement.where(Order.status.in_(statuses))
    if source is not None:
        statement = statement.where(Order.source == source)
    if search:
        pattern = f"%{search}%"
        statement = statement.where(or_(Order.order_number.ilike(pattern), Retailer.shop_name.ilike(pattern)))
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    page = db.scalars(
        statement.options(selectinload(Order.items), selectinload(Order.retailer))
        .order_by(Order.created_at.desc(), Order.id)
        .offset(offset)
        .limit(limit)
    )
    return list(page), total


def count_by_status(db: Session) -> dict[str, int]:
    return dict(db.execute(select(Order.status, func.count()).group_by(Order.status)).tuples().all())
