import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.constants import OrderStatus
from app.models import Order, OrderItem


def approved_orders(
    db: Session, start: datetime | None, end: datetime | None, *,
    order_ids: list[uuid.UUID] | None = None, include_exported: bool = True, lock: bool = False,
) -> list[Order]:
    """APPROVED orders confirmed in [start, end), oldest first, with items and retailer."""
    statement = (
        select(Order)
        .where(Order.status == OrderStatus.APPROVED)
        .options(selectinload(Order.items).selectinload(OrderItem.product), selectinload(Order.retailer))
        .order_by(Order.approved_at, Order.order_number)
    )
    if start is not None:
        statement = statement.where(Order.approved_at >= start)
    if end is not None:
        statement = statement.where(Order.approved_at < end)
    if order_ids is not None:
        statement = statement.where(Order.id.in_(order_ids))
    if not include_exported:
        statement = statement.where(Order.tally_exported_at.is_(None))
    if lock:
        statement = statement.with_for_update(of=Order).execution_options(populate_existing=True)
    return list(db.scalars(statement))
