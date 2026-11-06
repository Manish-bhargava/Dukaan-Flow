import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, aliased, selectinload

from app.core.constants import OrderStatus, UserRole
from app.models import AiExtraction, Order, OrderEvent, OrderItem, Retailer, User

_ORDER_LOAD = (
    selectinload(Order.items).selectinload(OrderItem.product),
    selectinload(Order.retailer).selectinload(Retailer.assigned_salesman),
    selectinload(Order.creator),
    selectinload(Order.approver),
    selectinload(Order.ai_extraction).selectinload(AiExtraction.items),
)


def _filtered(
    statuses: Sequence[str], source: str | None, search: str | None, salesman_id: uuid.UUID | None,
    date_column, start: datetime | None, end: datetime | None, exported: bool | None,
    retailer_id: uuid.UUID | None = None,
) -> Select:
    creator = aliased(User)
    statement = select(Order).join(Order.retailer).join(creator, Order.creator)
    if statuses:
        statement = statement.where(Order.status.in_(statuses))
    if source is not None:
        statement = statement.where(Order.source == source)
    if retailer_id is not None:
        statement = statement.where(Order.retailer_id == retailer_id)
    if search:
        pattern = f"%{search}%"
        statement = statement.where(or_(
            Order.order_number.ilike(pattern), Retailer.shop_name.ilike(pattern),
            Retailer.owner_name.ilike(pattern), Retailer.phone.ilike(pattern),
        ))
    if salesman_id is not None:
        # Placed by the salesman, or placed for one of the salesman's shops by someone else.
        statement = statement.where(or_(
            Order.created_by == salesman_id,
            and_(creator.role != UserRole.SALESMAN, Retailer.assigned_salesman_id == salesman_id),
        ))
    if start is not None:
        statement = statement.where(date_column >= start)
    if end is not None:
        statement = statement.where(date_column < end)
    if exported is not None:
        statement = statement.where(Order.tally_exported_at.is_not(None) if exported else Order.tally_exported_at.is_(None))
    return statement


def search_orders(
    db: Session, *, statuses: Sequence[str], source: str | None, search: str | None,
    salesman_id: uuid.UUID | None, date_column, start: datetime | None, end: datetime | None,
    exported: bool | None, order_by: Sequence, offset: int, limit: int, retailer_id: uuid.UUID | None = None,
) -> tuple[list[Order], int]:
    statement = _filtered(statuses, source, search, salesman_id, date_column, start, end, exported, retailer_id)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    page = db.scalars(statement.options(*_ORDER_LOAD).order_by(*order_by, Order.id).offset(offset).limit(limit))
    return list(page), total


def get_order(db: Session, order_id: uuid.UUID) -> Order | None:
    return db.scalar(select(Order).where(Order.id == order_id).options(*_ORDER_LOAD))


def orders_with_statuses(db: Session, statuses: Sequence[str]) -> list[Order]:
    return list(db.scalars(select(Order).where(Order.status.in_(statuses)).options(*_ORDER_LOAD)))


def approved_between(db: Session, start: datetime | None, end: datetime | None,
                     salesman_id: uuid.UUID | None) -> list[Order]:
    statement = _filtered([OrderStatus.APPROVED], None, None, salesman_id, Order.approved_at, start, end, None)
    return list(db.scalars(statement.options(*_ORDER_LOAD).order_by(Retailer.shop_name, Order.approved_at)))


def count_created_between(db: Session, start: datetime, end: datetime) -> int:
    return db.scalar(select(func.count()).where(Order.created_at >= start, Order.created_at < end)) or 0


def count_status_between(db: Session, status: str, column, start: datetime, end: datetime) -> int:
    return db.scalar(select(func.count()).where(Order.status == status, column >= start, column < end)) or 0


def count_events_between(db: Session, action: str, start: datetime, end: datetime) -> int:
    return db.scalar(select(func.count()).where(
        OrderEvent.action == action, OrderEvent.created_at >= start, OrderEvent.created_at < end)) or 0


def count_by_status(db: Session) -> dict[str, int]:
    return dict(db.execute(select(Order.status, func.count()).group_by(Order.status)).tuples().all())


def count_not_exported(db: Session) -> int:
    return db.scalar(select(func.count()).where(
        Order.status == OrderStatus.APPROVED, Order.tally_exported_at.is_(None))) or 0


def last_events(db: Session, order_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, OrderEvent]:
    """The latest history entry of each order."""
    ids = list(order_ids)
    if not ids:
        return {}
    ranked = (
        select(OrderEvent.id, func.row_number().over(
            partition_by=OrderEvent.order_id, order_by=(OrderEvent.created_at.desc(), OrderEvent.id.desc())).label("n"))
        .where(OrderEvent.order_id.in_(ids)).subquery()
    )
    events = db.scalars(select(OrderEvent).join(ranked, ranked.c.id == OrderEvent.id).where(ranked.c.n == 1)
                        .options(selectinload(OrderEvent.actor)))
    return {e.order_id: e for e in events}


def events_for(db: Session, order_id: uuid.UUID) -> list[OrderEvent]:
    return list(db.scalars(select(OrderEvent).where(OrderEvent.order_id == order_id)
                           .options(selectinload(OrderEvent.actor))
                           .order_by(OrderEvent.created_at, OrderEvent.id)))


def similar_recent_orders(db: Session, retailer_ids: Iterable[uuid.UUID], start: datetime, end: datetime) -> list[Order]:
    """Non-rejected orders of these retailers in [start, end), with items (duplicate check)."""
    ids = list(retailer_ids)
    if not ids:
        return []
    return list(db.scalars(
        select(Order).where(Order.retailer_id.in_(ids), Order.status != OrderStatus.REJECTED,
                            Order.created_at >= start, Order.created_at < end)
        .options(selectinload(Order.items))
    ))


def salesmen(db: Session) -> list[User]:
    return list(db.scalars(select(User).where(User.role == UserRole.SALESMAN).order_by(User.name)))
