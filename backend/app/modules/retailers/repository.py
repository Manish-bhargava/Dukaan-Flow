import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CreditAccount, CreditLedger, Order, Retailer


def get_retailer(db: Session, retailer_id: uuid.UUID) -> Retailer | None:
    return db.get(Retailer, retailer_id)


def get_assigned_retailer_ids(db: Session, salesman_id: uuid.UUID) -> list[uuid.UUID]:
    statement = select(Retailer.id).where(Retailer.assigned_salesman_id == salesman_id)
    return list(db.scalars(statement))


def get_credit_account(
    db: Session, retailer_id: uuid.UUID, lock: bool = False
) -> CreditAccount | None:
    statement = select(CreditAccount).where(CreditAccount.retailer_id == retailer_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return db.scalar(statement)


def add_ledger_entry(db: Session, entry: CreditLedger) -> None:
    db.add(entry)


def order_stats(db: Session, retailer_id: uuid.UUID) -> dict[str, tuple[int, object]]:
    """{status: (number of orders, sum of grand_total)} for one retailer."""
    statement = (
        select(Order.status, func.count(), func.coalesce(func.sum(Order.grand_total), 0))
        .where(Order.retailer_id == retailer_id)
        .group_by(Order.status)
    )
    return {status: (count, total) for status, count, total in db.execute(statement)}


def reserved_credit(db: Session, retailer_id: uuid.UUID, exclude_order_id: uuid.UUID | None = None):
    """Sum of grand totals of the retailer's orders awaiting the Order Desk (PENDING, ON_HOLD,
    CLARIFICATION_REQUIRED). They hold credit until confirmed (then outstanding) or rejected
    (released). CREDIT_HOLD orders do not hold credit: they are already above it and wait
    for an override."""
    from app.core.constants import CREDIT_RESERVING_STATUSES

    statement = select(func.coalesce(func.sum(Order.grand_total), 0)).where(
        Order.retailer_id == retailer_id, Order.status.in_(CREDIT_RESERVING_STATUSES)
    )
    if exclude_order_id is not None:
        statement = statement.where(Order.id != exclude_order_id)
    return db.scalar(statement)
