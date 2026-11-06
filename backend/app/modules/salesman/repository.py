import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Order, Retailer, ShopVisit, User


def assigned_active_retailers(db: Session, salesman_id: uuid.UUID) -> list[Retailer]:
    statement = (
        select(Retailer)
        .where(Retailer.assigned_salesman_id == salesman_id, Retailer.is_active.is_(True))
        .order_by(Retailer.shop_name)
    )
    return list(db.scalars(statement))


def recent_orders(db: Session, retailer_id: uuid.UUID, limit: int = 5) -> list[Order]:
    statement = (
        select(Order)
        .where(Order.retailer_id == retailer_id)
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(statement))


def retailer_login_phones(db: Session, retailer_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    """Mobile numbers of each retailer's active login accounts (users.phone)."""
    statement = (
        select(User.retailer_id, User.phone)
        .where(User.retailer_id.in_(retailer_ids), User.is_active.is_(True))
        .order_by(User.phone)
    )
    phones: dict[uuid.UUID, list[str]] = {}
    for retailer_id, phone in db.execute(statement):
        phones.setdefault(retailer_id, []).append(phone)
    return phones


def orders_created_between(db: Session, user_id: uuid.UUID, start: datetime, end: datetime) -> int:
    from sqlalchemy import func

    statement = select(func.count()).select_from(Order).where(
        Order.created_by == user_id, Order.created_at >= start, Order.created_at < end
    )
    return db.scalar(statement) or 0


def get_visit(db: Session, visit_id: uuid.UUID) -> ShopVisit | None:
    return db.get(ShopVisit, visit_id)


def visits_between(db: Session, salesman_id: uuid.UUID, start: datetime, end: datetime) -> list[ShopVisit]:
    statement = (
        select(ShopVisit)
        .where(ShopVisit.salesman_id == salesman_id, ShopVisit.started_at >= start, ShopVisit.started_at < end)
        .order_by(ShopVisit.started_at.desc())
    )
    return list(db.scalars(statement))
