"""Database queries for the Admin module."""

import uuid
from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, String, and_, case, cast, func, literal, null, or_, select, union_all
from sqlalchemy.orm import Session, aliased, joinedload, selectinload

from app.core.constants import OrderStatus, UserRole
from app.models import (
    AiExtraction,
    AuditLog,
    Brand,
    Category,
    CreditAccount,
    CreditLedger,
    Inventory,
    Order,
    OrderEvent,
    OrderItem,
    Product,
    Retailer,
    RetailerPrice,
    SalesmanSyncStatus,
    Scheme,
    ShopVisit,
    StockMovement,
    User,
)


def _page(db: Session, statement: Select, order_by, offset: int, limit: int) -> tuple[list, int]:
    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
    return list(db.scalars(statement.order_by(*order_by).offset(offset).limit(limit)).unique()), total


# ---------------------------------------------------------------- retailers


def last_order_subquery():
    return (select(Order.retailer_id, func.max(Order.created_at).label("last_order_at"))
            .group_by(Order.retailer_id).subquery())


def purchases_subquery():
    return (select(Order.retailer_id, func.sum(Order.grand_total).label("purchased"))
            .where(Order.status == OrderStatus.APPROVED).group_by(Order.retailer_id).subquery())


def search_retailers(db: Session, *, search: str | None, status: str | None, salesman_id: str | None,
                     sort: str, offset: int, limit: int):
    last = last_order_subquery()
    bought = purchases_subquery()
    statement = (
        select(Retailer, CreditAccount, last.c.last_order_at, bought.c.purchased)
        .outerjoin(CreditAccount, CreditAccount.retailer_id == Retailer.id)
        .outerjoin(last, last.c.retailer_id == Retailer.id)
        .outerjoin(bought, bought.c.retailer_id == Retailer.id)
        .options(joinedload(Retailer.assigned_salesman))
    )
    if search:
        p = f"%{search}%"
        statement = statement.where(or_(Retailer.shop_name.ilike(p), Retailer.owner_name.ilike(p),
                                        Retailer.phone.ilike(p), Retailer.city.ilike(p), cast(Retailer.id, String).ilike(p)))
    if status == "active":
        statement = statement.where(Retailer.is_active.is_(True))
    elif status == "inactive":
        statement = statement.where(Retailer.is_active.is_(False))
    elif status == "restricted":
        statement = statement.where(Retailer.ordering_restricted_reason.is_not(None))
    if salesman_id == "none":
        statement = statement.where(Retailer.assigned_salesman_id.is_(None))
    elif salesman_id:
        statement = statement.where(Retailer.assigned_salesman_id == uuid.UUID(salesman_id))
    order = {
        "name": (Retailer.shop_name,),
        "newest": (Retailer.created_at.desc(),),
        "outstanding": (CreditAccount.current_outstanding.desc().nulls_last(), Retailer.shop_name),
        "last_order": (last.c.last_order_at.desc().nulls_last(), Retailer.shop_name),
        "purchased": (bought.c.purchased.desc().nulls_last(), Retailer.shop_name),
    }[sort]
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.execute(statement.order_by(*order, Retailer.id).offset(offset).limit(limit)).unique().all()
    return rows, total


def retailer_users(db: Session, retailer_id: uuid.UUID) -> list[User]:
    return list(db.scalars(select(User).where(User.retailer_id == retailer_id).order_by(User.created_at)))


def user_by_phone(db: Session, phone: str) -> User | None:
    return db.scalar(select(User).where(User.phone == phone))


def user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def recent_orders(db: Session, *, retailer_id=None, created_by=None, limit=10) -> list[Order]:
    statement = select(Order).options(selectinload(Order.items), joinedload(Order.retailer))
    if retailer_id:
        statement = statement.where(Order.retailer_id == retailer_id)
    if created_by:
        statement = statement.where(Order.created_by == created_by)
    return list(db.scalars(statement.order_by(Order.created_at.desc()).limit(limit)).unique())


def ledger(db: Session, retailer_id: uuid.UUID, limit: int = 200) -> list[tuple[CreditLedger, str | None, str | None]]:
    statement = (
        select(CreditLedger, Order.order_number, User.name)
        .outerjoin(Order, Order.id == CreditLedger.order_id)
        .outerjoin(User, User.id == CreditLedger.created_by)
        .where(CreditLedger.retailer_id == retailer_id)
        .order_by(CreditLedger.created_at.desc(), CreditLedger.id).limit(limit)
    )
    return list(db.execute(statement).tuples())


def credit_totals(db: Session) -> tuple[Decimal, Decimal]:
    row = db.execute(select(func.coalesce(func.sum(CreditAccount.current_outstanding), 0),
                            func.coalesce(func.sum(CreditAccount.credit_limit), 0))).one()
    return row[0], row[1]


# ---------------------------------------------------------------- users / salesmen


def search_users(db: Session, *, role: str | None, search: str | None, status: str | None, offset: int, limit: int):
    statement = select(User).options(joinedload(User.retailer))
    if role:
        statement = statement.where(User.role == role)
    if status == "active":
        statement = statement.where(User.is_active.is_(True))
    elif status == "inactive":
        statement = statement.where(User.is_active.is_(False))
    if search:
        p = f"%{search}%"
        statement = statement.where(or_(User.name.ilike(p), User.phone.ilike(p), User.email.ilike(p)))
    return _page(db, statement, (User.role, User.name), offset, limit)


def count_active_admins(db: Session) -> int:
    return db.scalar(select(func.count()).where(User.role == UserRole.ADMIN, User.is_active.is_(True))) or 0


def assigned_retailers(db: Session, salesman_id: uuid.UUID) -> list[Retailer]:
    return list(db.scalars(select(Retailer).where(Retailer.assigned_salesman_id == salesman_id)
                           .options(joinedload(Retailer.credit_account)).order_by(Retailer.shop_name)))


def assigned_counts(db: Session) -> dict[uuid.UUID, int]:
    rows = db.execute(select(Retailer.assigned_salesman_id, func.count())
                      .where(Retailer.assigned_salesman_id.is_not(None)).group_by(Retailer.assigned_salesman_id))
    return dict(rows.tuples().all())


def salesman_order_stats(db: Session, since: datetime) -> dict[uuid.UUID, tuple[int, Decimal, int]]:
    """Per salesman since `since`: orders placed, value of those confirmed, offline orders."""
    rows = db.execute(
        select(Order.created_by, func.count(),
               func.coalesce(func.sum(case((Order.status == OrderStatus.APPROVED, Order.grand_total), else_=0)), 0),
               func.count().filter(Order.created_offline.is_(True)))
        .join(User, User.id == Order.created_by).where(User.role == UserRole.SALESMAN, Order.created_at >= since)
        .group_by(Order.created_by))
    return {r[0]: (r[1], r[2], r[3]) for r in rows}


def visit_stats(db: Session, since: datetime) -> dict[uuid.UUID, tuple[int, int, datetime | None]]:
    """Per salesman since `since`: visits, visits that produced an order, last visit time."""
    rows = db.execute(
        select(ShopVisit.salesman_id, func.count(), func.count().filter(ShopVisit.order_id.is_not(None)),
               func.max(ShopVisit.started_at))
        .where(ShopVisit.started_at >= since).group_by(ShopVisit.salesman_id))
    return {r[0]: (r[1], r[2], r[3]) for r in rows}


def last_visits(db: Session) -> dict[uuid.UUID, datetime]:
    return dict(db.execute(select(ShopVisit.salesman_id, func.max(ShopVisit.started_at))
                           .group_by(ShopVisit.salesman_id)).tuples().all())


def visits(db: Session, salesman_id: uuid.UUID, limit: int = 100) -> list[tuple[ShopVisit, str, str | None, str | None]]:
    statement = (
        select(ShopVisit, Retailer.shop_name, Order.order_number, Order.status)
        .join(Retailer, Retailer.id == ShopVisit.retailer_id)
        .outerjoin(Order, Order.id == ShopVisit.order_id)
        .where(ShopVisit.salesman_id == salesman_id)
        .order_by(ShopVisit.started_at.desc()).limit(limit)
    )
    return list(db.execute(statement).tuples())


def sync_statuses(db: Session) -> dict[uuid.UUID, SalesmanSyncStatus]:
    return {s.user_id: s for s in db.scalars(select(SalesmanSyncStatus))}


def user_activity_counts(db: Session, user_id: uuid.UUID) -> dict[str, int]:
    return {
        "orders_created": db.scalar(select(func.count()).where(Order.created_by == user_id)) or 0,
        "order_actions": db.scalar(select(func.count()).where(OrderEvent.actor_id == user_id,
                                                              OrderEvent.action != "RECEIVED")) or 0,
        "visits": db.scalar(select(func.count()).where(ShopVisit.salesman_id == user_id)) or 0,
        "admin_changes": db.scalar(select(func.count()).where(AuditLog.actor_id == user_id)) or 0,
    }


# ---------------------------------------------------------------- catalogue


def categories_with_counts(db: Session) -> list[tuple[Category, int]]:
    counts = select(Product.category_id, func.count().label("n")).group_by(Product.category_id).subquery()
    return list(db.execute(select(Category, func.coalesce(counts.c.n, 0))
                           .outerjoin(counts, counts.c.category_id == Category.id).order_by(Category.name)).tuples())


def brands_with_counts(db: Session) -> list[tuple[Brand, int]]:
    counts = select(Product.brand, func.count().label("n")).group_by(Product.brand).subquery()
    return list(db.execute(select(Brand, func.coalesce(counts.c.n, 0))
                           .outerjoin(counts, counts.c.brand == Brand.name).order_by(Brand.name)).tuples())


def default_prices(db: Session, at: datetime, product_ids: Iterable[uuid.UUID] | None = None) -> dict[uuid.UUID, RetailerPrice]:
    statement = select(RetailerPrice).where(
        RetailerPrice.retailer_id.is_(None), RetailerPrice.effective_from <= at,
        or_(RetailerPrice.effective_to.is_(None), RetailerPrice.effective_to > at))
    if product_ids is not None:
        statement = statement.where(RetailerPrice.product_id.in_(list(product_ids)))
    return {p.product_id: p for p in db.scalars(statement)}


def own_prices(db: Session, retailer_id: uuid.UUID, at: datetime) -> dict[uuid.UUID, RetailerPrice]:
    statement = select(RetailerPrice).where(
        RetailerPrice.retailer_id == retailer_id, RetailerPrice.effective_from <= at,
        or_(RetailerPrice.effective_to.is_(None), RetailerPrice.effective_to > at))
    return {p.product_id: p for p in db.scalars(statement)}


def override_counts(db: Session, at: datetime) -> dict[uuid.UUID, int]:
    rows = db.execute(select(RetailerPrice.product_id, func.count()).where(
        RetailerPrice.retailer_id.is_not(None), RetailerPrice.effective_from <= at,
        or_(RetailerPrice.effective_to.is_(None), RetailerPrice.effective_to > at)).group_by(RetailerPrice.product_id))
    return dict(rows.tuples().all())


def current_price_row(db: Session, product_id: uuid.UUID, retailer_id: uuid.UUID | None, at: datetime,
                      lock: bool = False) -> RetailerPrice | None:
    statement = select(RetailerPrice).where(
        RetailerPrice.product_id == product_id,
        RetailerPrice.retailer_id.is_(None) if retailer_id is None else RetailerPrice.retailer_id == retailer_id,
        RetailerPrice.effective_from <= at,
        or_(RetailerPrice.effective_to.is_(None), RetailerPrice.effective_to > at),
    ).order_by(RetailerPrice.effective_from.desc())
    if lock:
        statement = statement.with_for_update()
    return db.scalars(statement).first()


def price_history(db: Session, product_id: uuid.UUID, retailer_id: uuid.UUID | None = None, limit: int = 200):
    creator = aliased(User)
    statement = (
        select(RetailerPrice, Retailer.shop_name, creator.name)
        .outerjoin(Retailer, Retailer.id == RetailerPrice.retailer_id)
        .outerjoin(creator, creator.id == RetailerPrice.created_by)
        .where(RetailerPrice.product_id == product_id)
    )
    if retailer_id is not None:
        statement = statement.where(or_(RetailerPrice.retailer_id == retailer_id, RetailerPrice.retailer_id.is_(None)))
    return list(db.execute(statement.order_by(RetailerPrice.effective_from.desc(), RetailerPrice.created_at.desc())
                           .limit(limit)).tuples())


def search_products(db: Session, *, search, category_id, brand, status, stock, low_stock, offset, limit):
    statement = (select(Product, Inventory)
                 .outerjoin(Inventory, Inventory.product_id == Product.id)
                 .options(joinedload(Product.category)))
    if search:
        p = f"%{search}%"
        statement = statement.where(or_(Product.name.ilike(p), Product.sku.ilike(p), Product.brand.ilike(p)))
    if category_id:
        statement = statement.where(Product.category_id == category_id)
    if brand:
        statement = statement.where(Product.brand == brand)
    if status == "active":
        statement = statement.where(Product.is_active.is_(True))
    elif status == "inactive":
        statement = statement.where(Product.is_active.is_(False))
    stock_cases = func.coalesce(Inventory.stock_cases, 0)
    if stock == "out":
        statement = statement.where(stock_cases <= 0)
    elif stock == "low":
        statement = statement.where(stock_cases > 0, stock_cases <= low_stock)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.execute(statement.order_by(Product.name, Product.sku).offset(offset).limit(limit)).unique().all()
    return rows, total


def schemes(db: Session, *, product_search: str | None, product_id: uuid.UUID | None, state: str, now: datetime,
            offset: int, limit: int):
    statement = select(Scheme).join(Scheme.product).options(joinedload(Scheme.product))
    if product_id:
        statement = statement.where(Scheme.product_id == product_id)
    if product_search:
        p = f"%{product_search}%"
        statement = statement.where(or_(Product.name.ilike(p), Product.sku.ilike(p), Product.brand.ilike(p)))
    started = Scheme.starts_at <= now
    not_ended = or_(Scheme.ends_at.is_(None), Scheme.ends_at > now)
    if state == "active":
        statement = statement.where(Scheme.is_active.is_(True), started, not_ended)
    elif state == "upcoming":
        statement = statement.where(Scheme.is_active.is_(True), Scheme.starts_at > now)
    elif state == "expired":
        statement = statement.where(Scheme.ends_at.is_not(None), Scheme.ends_at <= now)
    elif state == "inactive":
        statement = statement.where(Scheme.is_active.is_(False))
    return _page(db, statement, (Product.name, Scheme.min_quantity), offset, limit)


def overlapping_schemes(db: Session, product_id: uuid.UUID, starts_at: datetime, ends_at: datetime | None,
                        exclude_id: uuid.UUID | None = None) -> list[Scheme]:
    """Active schemes of the product whose date window overlaps [starts_at, ends_at)."""
    statement = select(Scheme).where(
        Scheme.product_id == product_id, Scheme.is_active.is_(True),
        or_(Scheme.ends_at.is_(None), Scheme.ends_at > starts_at),
    )
    if ends_at is not None:
        statement = statement.where(Scheme.starts_at < ends_at)
    if exclude_id is not None:
        statement = statement.where(Scheme.id != exclude_id)
    return list(db.scalars(statement))


def lock_inventory_row(db: Session, product_id: uuid.UUID) -> Inventory | None:
    return db.scalar(select(Inventory).where(Inventory.product_id == product_id).with_for_update()
                     .execution_options(populate_existing=True))


def last_movements(db: Session, product_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, datetime]:
    return dict(db.execute(select(StockMovement.product_id, func.max(StockMovement.created_at))
                           .where(StockMovement.product_id.in_(list(product_ids)))
                           .group_by(StockMovement.product_id)).tuples().all())


def stock_history(db: Session, product_id: uuid.UUID, limit: int = 200):
    """Movements newest first, with the stock after each (stored, else the running sum)."""
    running = func.sum(StockMovement.quantity).over(
        partition_by=StockMovement.product_id, order_by=(StockMovement.created_at, StockMovement.id))
    inner = (select(StockMovement.id.label("id"), running.label("running"))
             .where(StockMovement.product_id == product_id).subquery())
    statement = (
        select(StockMovement, func.coalesce(StockMovement.stock_after, inner.c.running), User.name, Order.order_number)
        .join(inner, inner.c.id == StockMovement.id)
        .outerjoin(User, User.id == StockMovement.created_by)
        .outerjoin(Order, Order.id == StockMovement.order_id)
        .order_by(StockMovement.created_at.desc(), StockMovement.id.desc()).limit(limit)
    )
    return list(db.execute(statement).tuples())


def low_stock(db: Session, threshold: int, limit: int | None = None):
    statement = (select(Product, func.coalesce(Inventory.stock_cases, 0))
                 .outerjoin(Inventory, Inventory.product_id == Product.id)
                 .where(Product.is_active.is_(True), func.coalesce(Inventory.stock_cases, 0) <= threshold)
                 .order_by(func.coalesce(Inventory.stock_cases, 0), Product.name))
    if limit:
        statement = statement.limit(limit)
    return list(db.execute(statement).tuples())


# ---------------------------------------------------------------- dashboard / monitoring


def count(db: Session, model, *where) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where)) or 0


def status_counts(db: Session) -> dict[str, int]:
    return dict(db.execute(select(Order.status, func.count()).group_by(Order.status)).tuples().all())


def confirmed_value(db: Session, start: datetime | None = None, end: datetime | None = None) -> Decimal:
    statement = select(func.coalesce(func.sum(Order.grand_total), 0)).where(Order.status == OrderStatus.APPROVED)
    if start:
        statement = statement.where(Order.approved_at >= start)
    if end:
        statement = statement.where(Order.approved_at < end)
    return db.scalar(statement)


def inactive_retailers(db: Session, before: datetime, limit: int | None = None):
    """Active retailers whose last order is before `before` (or who never ordered)."""
    last = last_order_subquery()
    statement = (select(Retailer, last.c.last_order_at)
                 .outerjoin(last, last.c.retailer_id == Retailer.id)
                 .options(joinedload(Retailer.assigned_salesman))
                 .where(Retailer.is_active.is_(True), or_(last.c.last_order_at.is_(None), last.c.last_order_at < before))
                 .order_by(last.c.last_order_at.asc().nulls_first(), Retailer.shop_name))
    if limit:
        statement = statement.limit(limit)
    return list(db.execute(statement).unique().tuples())


def recent_retailers(db: Session, limit: int) -> list[Retailer]:
    return list(db.scalars(select(Retailer).options(joinedload(Retailer.assigned_salesman))
                           .order_by(Retailer.created_at.desc()).limit(limit)))


def recent_products(db: Session, limit: int) -> list[Product]:
    return list(db.scalars(select(Product).options(joinedload(Product.category))
                           .order_by(Product.created_at.desc()).limit(limit)))


def recent_salesman_visits(db: Session, limit: int):
    return list(db.execute(
        select(ShopVisit, User.name, Retailer.shop_name, Order.order_number, Order.grand_total)
        .join(User, User.id == ShopVisit.salesman_id).join(Retailer, Retailer.id == ShopVisit.retailer_id)
        .outerjoin(Order, Order.id == ShopVisit.order_id)
        .order_by(ShopVisit.started_at.desc()).limit(limit)).tuples())


def desk_event_counts(db: Session, since: datetime) -> list[tuple[uuid.UUID, str, str, str, int]]:
    """Order Desk / Admin actions per user and action since `since`."""
    return list(db.execute(
        select(User.id, User.name, User.role, OrderEvent.action, func.count())
        .join(User, User.id == OrderEvent.actor_id)
        .where(OrderEvent.created_at >= since, User.role.in_((UserRole.ORDER_DESK, UserRole.ADMIN)),
               OrderEvent.action != "RECEIVED")
        .group_by(User.id, User.name, User.role, OrderEvent.action)).tuples())


def corrected_order_count(db: Session, since: datetime | None = None) -> int:
    statement = select(func.count(func.distinct(OrderEvent.order_id))).where(OrderEvent.action == "CORRECTED")
    if since:
        statement = statement.where(OrderEvent.created_at >= since)
    return db.scalar(statement) or 0


def exported_counts(db: Session) -> tuple[int, int]:
    row = db.execute(select(func.count().filter(Order.tally_exported_at.is_not(None)),
                            func.count().filter(Order.tally_exported_at.is_(None)))
                     .where(Order.status == OrderStatus.APPROVED)).one()
    return row[0], row[1]


def audit_entries(db: Session, *, source: str, entity_type: str | None, action: str | None, entity_id: str | None = None,
                  actor_id: uuid.UUID | None, search: str | None, start: datetime | None, end: datetime | None,
                  offset: int, limit: int):
    """Master-data audit entries and order history merged, newest first."""
    master = (select(AuditLog.id.label("id"), AuditLog.created_at.label("at"), AuditLog.actor_id.label("actor_id"),
                     AuditLog.action.label("action"), AuditLog.entity_type.label("entity_type"),
                     AuditLog.entity_id.label("entity_id"), AuditLog.entity_label.label("label"),
                     AuditLog.details.label("details"), cast(null(), String).label("message")))
    orders = (select(OrderEvent.id.label("id"), OrderEvent.created_at.label("at"), OrderEvent.actor_id.label("actor_id"),
                     ("ORDER_" + OrderEvent.action).label("action"), literal("order").label("entity_type"),
                     cast(OrderEvent.order_id, String).label("entity_id"), Order.order_number.label("label"),
                     OrderEvent.details.label("details"), OrderEvent.message.label("message"))
              .join(Order, Order.id == OrderEvent.order_id))
    parts = {"master": [master], "orders": [orders]}.get(source, [master, orders])
    merged = union_all(*parts).subquery() if len(parts) > 1 else parts[0].subquery()
    statement = select(merged, User.name.label("actor_name"), User.role.label("actor_role")).outerjoin(
        User, User.id == merged.c.actor_id)
    if entity_type:
        statement = statement.where(merged.c.entity_type == entity_type)
    if action:
        statement = statement.where(merged.c.action == action)
    if entity_id:
        statement = statement.where(merged.c.entity_id == entity_id)
    if actor_id:
        statement = statement.where(merged.c.actor_id == actor_id)
    if search:
        statement = statement.where(merged.c.label.ilike(f"%{search}%"))
    if start:
        statement = statement.where(merged.c.at >= start)
    if end:
        statement = statement.where(merged.c.at < end)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.execute(statement.order_by(merged.c.at.desc(), merged.c.id).offset(offset).limit(limit)).mappings().all()
    return list(rows), total


def ai_extractions(db: Session, *, state: str | None, offset: int, limit: int):
    order = aliased(Order)
    statement = (select(AiExtraction, order)
                 .outerjoin(order, order.ai_extraction_id == AiExtraction.id)
                 .options(selectinload(AiExtraction.items)))
    if state == "draft":
        statement = statement.where(order.id.is_(None))
    elif state == "ordered":
        statement = statement.where(order.id.is_not(None))
    elif state in ("APPROVED", "REJECTED"):
        statement = statement.where(order.status == state)
    elif state == "open":
        statement = statement.where(order.status.in_(("PENDING", "CREDIT_HOLD", "ON_HOLD", "CLARIFICATION_REQUIRED")))
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.execute(statement.order_by(AiExtraction.created_at.desc()).offset(offset).limit(limit)).unique().all()
    return rows, total


def ai_stats(db: Session) -> dict:
    from app.models import AiExtractionItem

    order = aliased(Order)
    row = db.execute(select(func.count(func.distinct(AiExtraction.id)), func.count(func.distinct(order.id)),
                            func.count(func.distinct(order.id)).filter(order.status == OrderStatus.APPROVED),
                            func.count(func.distinct(order.id)).filter(order.status == OrderStatus.REJECTED))
                     .select_from(AiExtraction).outerjoin(order, order.ai_extraction_id == AiExtraction.id)).one()
    items = db.execute(select(func.count(), func.avg(AiExtractionItem.confidence),
                              func.count().filter(AiExtractionItem.requires_clarification.is_(True)))).one()
    return {"extractions": row[0], "ordered": row[1], "confirmed": row[2], "rejected": row[3],
            "lines": items[0], "average_confidence": items[1], "clarification_lines": items[2]}


def offline_orders(db: Session, limit: int = 100) -> list[Order]:
    return list(db.scalars(select(Order).where(Order.created_offline.is_(True))
                           .options(joinedload(Order.retailer), joinedload(Order.creator))
                           .order_by(Order.created_at.desc()).limit(limit)).unique())


def offline_counts(db: Session) -> dict[str, int]:
    rows = db.execute(select(Order.status, func.count()).where(Order.created_offline.is_(True)).group_by(Order.status))
    return dict(rows.tuples().all())


def sync_failures(db: Session, since: datetime | None = None, limit: int = 100) -> list[AuditLog]:
    statement = select(AuditLog).where(AuditLog.action == "SYNC_FAILED").options(joinedload(AuditLog.actor))
    if since:
        statement = statement.where(AuditLog.created_at >= since)
    return list(db.scalars(statement.order_by(AuditLog.created_at.desc()).limit(limit)))


# ---------------------------------------------------------------- reports


def approved_orders_between(db: Session, start: datetime | None, end: datetime | None) -> list[Order]:
    statement = (select(Order).where(Order.status == OrderStatus.APPROVED)
                 .options(selectinload(Order.items).joinedload(OrderItem.product).joinedload(Product.category),
                          joinedload(Order.retailer).joinedload(Retailer.assigned_salesman), joinedload(Order.creator)))
    if start:
        statement = statement.where(Order.approved_at >= start)
    if end:
        statement = statement.where(Order.approved_at < end)
    return list(db.scalars(statement).unique())


def orders_created_between(db: Session, start: datetime | None, end: datetime | None) -> list[Order]:
    statement = select(Order).options(joinedload(Order.creator), joinedload(Order.retailer))
    if start:
        statement = statement.where(Order.created_at >= start)
    if end:
        statement = statement.where(Order.created_at < end)
    return list(db.scalars(statement).unique())


def visits_between(db: Session, start: datetime | None, end: datetime | None) -> list[ShopVisit]:
    statement = select(ShopVisit)
    if start:
        statement = statement.where(ShopVisit.started_at >= start)
    if end:
        statement = statement.where(ShopVisit.started_at < end)
    return list(db.scalars(statement))


def credit_report(db: Session):
    last = last_order_subquery()
    return list(db.execute(
        select(Retailer, CreditAccount, last.c.last_order_at)
        .join(CreditAccount, CreditAccount.retailer_id == Retailer.id)
        .outerjoin(last, last.c.retailer_id == Retailer.id)
        .options(joinedload(Retailer.assigned_salesman))
        .order_by(CreditAccount.current_outstanding.desc(), Retailer.shop_name)).unique().tuples())


def salesmen(db: Session, active_only: bool = False) -> list[User]:
    statement = select(User).where(User.role == UserRole.SALESMAN)
    if active_only:
        statement = statement.where(User.is_active.is_(True))
    return list(db.scalars(statement.order_by(User.name)))

