from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.constants import OrderStatus
from app.models import Order, OrderItem


def approved_orders(db: Session, start: datetime | None, end: datetime | None) -> list[Order]:
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
    return list(db.scalars(statement))
