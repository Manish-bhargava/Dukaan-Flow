import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.core.constants import ORDER_DESK_ROLES, ErrorCode, OrderEventAction
from app.core.permissions import ensure_role
from app.exceptions.base import AppException
from app.models import User
from app.modules.exports import repository, tally


def _range(from_date: date | None, to_date: date | None) -> tuple[datetime | None, datetime | None]:
    if from_date and to_date and from_date > to_date:
        raise AppException("from_date must not be after to_date", ErrorCode.VALIDATION_ERROR, 422)
    start = datetime.combine(from_date, time.min, tally.IST) if from_date else None
    end = datetime.combine(to_date + timedelta(days=1), time.min, tally.IST) if to_date else None
    return start, end


def tally_orders_csv(db: Session, actor: User, from_date: date | None, to_date: date | None) -> str:
    """Read-only download of confirmed orders whose confirmation date (IST) is within
    from_date..to_date, inclusive. Does not mark anything as exported."""
    ensure_role(actor, *ORDER_DESK_ROLES)
    return tally.to_csv(repository.approved_orders(db, *_range(from_date, to_date)))


def export_to_tally(
    db: Session, actor: User, *, from_date: date | None, to_date: date | None,
    order_ids: list[uuid.UUID] | None, include_exported: bool,
) -> tuple[str, int]:
    """Tally export that records itself: the chosen confirmed orders (by ids and/or IST
    confirmation dates) are written to CSV and marked exported, with an EXPORTED entry in
    each order's history. Orders already exported are skipped unless include_exported (an
    explicit re-export), so an accidental second click never exports them twice."""
    from app.modules.orders.service import record_event

    ensure_role(actor, *ORDER_DESK_ROLES)
    try:
        orders = repository.approved_orders(db, *_range(from_date, to_date), order_ids=order_ids,
                                            include_exported=include_exported, lock=True)
        if not orders:
            raise AppException(
                "No confirmed orders to export" + ("" if include_exported else " (orders already exported are skipped)"),
                ErrorCode.NOTHING_TO_EXPORT, 409,
            )
        content = tally.to_csv(orders)
        now = datetime.now(UTC)
        for order in orders:
            again = order.tally_exported_at is not None
            record_event(db, order, OrderEventAction.EXPORTED, actor,
                         "Exported again to Tally" if again else "Exported to Tally",
                         {"re_export": again, "previously_exported_at": order.tally_exported_at.isoformat() if again else None})
            order.tally_exported_at = now
        db.commit()
        return content, len(orders)
    except Exception:
        db.rollback()
        raise
