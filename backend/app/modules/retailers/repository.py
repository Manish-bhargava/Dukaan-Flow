import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CreditAccount, CreditLedger, Retailer


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
