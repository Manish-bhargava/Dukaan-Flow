from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.core.constants import ORDER_DESK_ROLES, ErrorCode
from app.core.permissions import ensure_role
from app.exceptions.base import AppException
from app.models import User
from app.modules.exports import repository, tally


def tally_orders_csv(db: Session, actor: User, from_date: date | None, to_date: date | None) -> str:
    """Confirmed orders whose confirmation date (IST) is within from_date..to_date, inclusive."""
    ensure_role(actor, *ORDER_DESK_ROLES)
    if from_date and to_date and from_date > to_date:
        raise AppException("from_date must not be after to_date", ErrorCode.VALIDATION_ERROR, 422)
    start = datetime.combine(from_date, time.min, tally.IST) if from_date else None
    end = datetime.combine(to_date + timedelta(days=1), time.min, tally.IST) if to_date else None
    return tally.to_csv(repository.approved_orders(db, start, end))
