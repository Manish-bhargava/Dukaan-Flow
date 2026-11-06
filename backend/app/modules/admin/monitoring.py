"""Admin: dashboard, Order Desk oversight, AI orders, offline sync, audit log and settings.
Read-only views (except settings); the Admin does not bypass the Order Desk workflow or the
human confirmation of AI orders."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.constants import ErrorCode, OrderStatus, UserRole
from app.core.permissions import ensure_role
from app.exceptions.base import AppException
from app.models import Product, Retailer, User
from app.modules.admin import repository
from app.modules.admin.people import _committed
from app.modules.audit.service import record
from app.modules.order_desk import repository as desk_repository
from app.modules.order_desk import service as desk_service
from app.modules.settings.service import BusinessSettings, get_settings, save_settings

IST = ZoneInfo("Asia/Kolkata")


def ist_range(from_date: date | None, to_date: date | None) -> tuple[datetime | None, datetime | None]:
    if from_date and to_date and from_date > to_date:
        raise AppException("from_date must not be after to_date", ErrorCode.VALIDATION_ERROR, 422)
    start = datetime.combine(from_date, time.min, IST) if from_date else None
    end = datetime.combine(to_date + timedelta(days=1), time.min, IST) if to_date else None
    return start, end


def today_ist() -> tuple[datetime, datetime]:
    start = datetime.combine(datetime.now(IST).date(), time.min, IST)
    return start, start + timedelta(days=1)


def dashboard(db: Session, actor: User) -> dict:
    ensure_role(actor, UserRole.ADMIN)
    cfg = get_settings(db)
    start, end = today_ist()
    counts = repository.status_counts(db)
    outstanding, limits = repository.credit_totals(db)
    inactive_before = datetime.now(UTC) - timedelta(days=cfg.inactive_retailer_days)
    inactive = repository.inactive_retailers(db, inactive_before)
    low = repository.low_stock(db, cfg.low_stock_cases)
    return {
        "business_name": cfg.business_name,
        "retailers_total": repository.count(db, Retailer),
        "retailers_active": repository.count(db, Retailer, Retailer.is_active.is_(True)),
        "salesmen_total": repository.count(db, User, User.role == UserRole.SALESMAN),
        "salesmen_active": repository.count(db, User, User.role == UserRole.SALESMAN, User.is_active.is_(True)),
        "products_total": repository.count(db, Product),
        "products_active": repository.count(db, Product, Product.is_active.is_(True)),
        "orders_today": desk_repository.count_created_between(db, start, end),
        "pending": sum(counts.get(s, 0) for s in (OrderStatus.PENDING, OrderStatus.CREDIT_HOLD, OrderStatus.ON_HOLD)),
        "clarification": counts.get(OrderStatus.CLARIFICATION_REQUIRED, 0),
        "confirmed": counts.get(OrderStatus.APPROVED, 0),
        "rejected": counts.get(OrderStatus.REJECTED, 0),
        "confirmed_value_total": repository.confirmed_value(db),
        "confirmed_value_today": repository.confirmed_value(db, start, end),
        "confirmed_value_30d": repository.confirmed_value(db, start - timedelta(days=29), end),
        "outstanding_total": outstanding,
        "credit_limit_total": limits,
        "low_stock_threshold": cfg.low_stock_cases,
        "low_stock_count": len(low),
        "low_stock": low[:6],
        "inactive_days": cfg.inactive_retailer_days,
        "inactive_count": len(inactive),
        "inactive": inactive[:6],
        "recent_orders": repository.recent_orders(db, limit=8),
        "recent_retailers": repository.recent_retailers(db, 5),
        "recent_products": repository.recent_products(db, 5),
        "recent_visits": repository.recent_salesman_visits(db, 8),
    }


def order_desk_oversight(db: Session, actor: User) -> dict:
    ensure_role(actor, UserRole.ADMIN)
    since = datetime.now(UTC) - timedelta(days=30)
    exported, not_exported = repository.exported_counts(db)
    people: dict = {}
    for user_id, name, role, action, n in repository.desk_event_counts(db, since):
        person = people.setdefault(user_id, {"id": user_id, "name": name, "role": role, "actions": {}})
        person["actions"][action] = n
    recent, _ = repository.audit_entries(db, source="orders", entity_type=None, action=None, actor_id=None, search=None,
                                         start=None, end=None, offset=0, limit=25)
    return {
        "overview": desk_service.overview(db, actor),
        "corrected_orders_30d": repository.corrected_order_count(db, since),
        "corrected_orders_total": repository.corrected_order_count(db),
        "tally_exported": exported,
        "tally_not_exported": not_exported,
        "people": sorted(people.values(), key=lambda p: p["name"]),
        "recent": [r for r in recent if r["action"] != "ORDER_RECEIVED"][:20],
    }


def audit(db: Session, actor: User, *, source, entity_type, action, actor_id, search, from_date, to_date, page, limit):
    ensure_role(actor, UserRole.ADMIN)
    if source not in ("all", "master", "orders"):
        raise AppException("Unknown source", ErrorCode.VALIDATION_ERROR, 422)
    start, end = ist_range(from_date, to_date)
    return repository.audit_entries(db, source=source, entity_type=entity_type, action=action, actor_id=actor_id,
                                    search=(search or "").strip() or None, start=start, end=end,
                                    offset=(page - 1) * limit, limit=limit)


def ai_orders(db: Session, actor: User, *, state, page, limit):
    ensure_role(actor, UserRole.ADMIN)
    rows, total = repository.ai_extractions(db, state=state, offset=(page - 1) * limit, limit=limit)
    return {"rows": rows, "total": total, "stats": repository.ai_stats(db),
            "low_confidence": get_settings(db).ai_low_confidence_percent}


def sync_monitor(db: Session, actor: User) -> dict:
    ensure_role(actor, UserRole.ADMIN)
    statuses = repository.sync_statuses(db)
    week = datetime.now(UTC) - timedelta(days=7)
    return {
        "salesmen": [{"user": u, "sync": statuses.get(u.id)} for u in repository.salesmen(db)],
        "offline_counts": repository.offline_counts(db),
        "offline_orders": repository.offline_orders(db, 100),
        "failures": repository.sync_failures(db, limit=100),
        "failures_7d": len(repository.sync_failures(db, since=week, limit=10000)),
    }


def read_settings(db: Session, actor: User) -> BusinessSettings:
    ensure_role(actor, UserRole.ADMIN)
    return get_settings(db)


def update_settings(db: Session, actor: User, data: BusinessSettings) -> BusinessSettings:
    ensure_role(actor, UserRole.ADMIN)

    def work():
        saved, diff = save_settings(db, actor, data)
        if diff:
            record(db, actor, "SETTINGS_CHANGED", "settings", None, "Business settings", {"changes": diff})
        return saved

    return _committed(db, work)
