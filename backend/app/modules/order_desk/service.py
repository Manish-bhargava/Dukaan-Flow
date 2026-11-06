"""Order Desk: the office view over the one order system.

Lists, review data, validation warnings, overview counts and dispatch (loading) lists. All
order actions (confirm, reject, clarification, correction) go through `orders.service`; this
module only reads, so its warnings never change an order.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.constants import (
    ORDER_DESK_ROLES,
    ErrorCode,
    OrderEventAction,
    OrderSource,
    OrderStatus,
    UserRole,
)
from app.core.permissions import ensure_role
from app.exceptions.base import AppException
from app.models import Order, OrderEvent, User
from app.modules.inventory import repository as inventory_repository
from app.modules.order_desk import repository
from app.modules.orders import service as orders_service
from app.modules.retailers import repository as retailer_repository
from app.modules.retailers.service import credit_available, credit_summary
from app.modules.settings.service import get_settings

IST = ZoneInfo("Asia/Kolkata")

# Order Desk sections and the statuses they show.
VIEWS: dict[str, tuple[OrderStatus, ...]] = {
    "incoming": (OrderStatus.PENDING, OrderStatus.CREDIT_HOLD, OrderStatus.ON_HOLD),
    "clarification": (OrderStatus.CLARIFICATION_REQUIRED,),
    "confirmed": (OrderStatus.APPROVED,),
    "rejected": (OrderStatus.REJECTED,),
    "all": (),
}
OPEN = (OrderStatus.PENDING, OrderStatus.CREDIT_HOLD, OrderStatus.ON_HOLD, OrderStatus.CLARIFICATION_REQUIRED)
SORTS = {
    "newest": (Order.created_at.desc(),),
    "oldest": (Order.created_at.asc(),),
    "value_desc": (Order.grand_total.desc(), Order.created_at.desc()),
    "value_asc": (Order.grand_total.asc(), Order.created_at.desc()),
}


@dataclass(frozen=True)
class Warning:
    code: str
    severity: str  # "error": blocks confirmation as it is; "warning": the desk must look at it
    message: str


@dataclass
class DeskRow:
    order: Order
    salesman: User | None
    warnings: list[Warning]
    last_event: OrderEvent | None


@dataclass
class LineStock:
    item_id: uuid.UUID
    needed: Decimal
    available: Decimal

    @property
    def ok(self) -> bool:
        return self.needed <= self.available


@dataclass
class Review:
    order: Order
    salesman: User | None
    credit: object | None  # retailers.service.CreditSummary
    stock: list[LineStock]
    warnings: list[Warning]
    events: list[OrderEvent] = field(default_factory=list)


def _ist_range(from_date: date | None, to_date: date | None) -> tuple[datetime | None, datetime | None]:
    if from_date and to_date and from_date > to_date:
        raise AppException("from_date must not be after to_date", ErrorCode.VALIDATION_ERROR, 422)
    start = datetime.combine(from_date, time.min, IST) if from_date else None
    end = datetime.combine(to_date + timedelta(days=1), time.min, IST) if to_date else None
    return start, end


def _today() -> tuple[datetime, datetime]:
    start = datetime.combine(datetime.now(IST).date(), time.min, IST)
    return start, start + timedelta(days=1)


def salesman_of(order: Order) -> User | None:
    """The salesman who placed the order, else the salesman assigned to the shop."""
    if order.creator.role == UserRole.SALESMAN:
        return order.creator
    return order.retailer.assigned_salesman


def _signature(order: Order) -> frozenset:
    return frozenset((i.product_id, i.paid_quantity) for i in order.items)


# ---------------------------------------------------------------- warnings


def _warnings(db: Session, orders: Sequence[Order], *, with_prices: bool = True) -> dict[uuid.UUID, list[Warning]]:
    """Validation warnings for open orders (closed orders get none): stock, credit, data
    changed since placement (price, scheme, inactive product), offline changes found at
    sync, AI matching uncertainty and possible duplicates."""
    result: dict[uuid.UUID, list[Warning]] = {o.id: [] for o in orders}
    open_orders = [o for o in orders if o.status in OPEN]
    if not open_orders:
        return result
    cfg = get_settings(db)  # thresholds are Admin settings
    window = timedelta(hours=cfg.duplicate_window_hours)
    low_confidence = Decimal(cfg.ai_low_confidence_percent) / 100

    stock = inventory_repository.get_stock(db, {i.product_id for o in open_orders for i in o.items})
    earliest = min(o.created_at for o in open_orders) - window
    latest = max(o.created_at for o in open_orders) + window
    nearby = repository.similar_recent_orders(db, {o.retailer_id for o in open_orders}, earliest, latest)

    for order in open_orders:
        found = result[order.id]
        needed: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
        for item in order.items:
            needed[item.product_id] += item.paid_quantity + item.free_quantity
        for item in order.items:
            have = stock.get(item.product_id, Decimal(0))
            if needed[item.product_id] > have:
                found.append(Warning("INSUFFICIENT_STOCK", "error",
                                     f"{item.sku}: {_q(needed[item.product_id])} cases needed (incl. free), {_q(have)} in stock"))

        available = credit_available(db, order.retailer_id, exclude_order_id=order.id)
        if order.grand_total > available:
            found.append(Warning("CREDIT_LIMIT_EXCEEDED", "error",
                                 f"Order total Rs {order.grand_total:,.2f} is above the available credit "
                                 f"Rs {available:,.2f}; confirming needs a credit override reason"))

        if with_prices:
            for change in orders_service.current_changes(db, order):
                severity = "error" if change["code"] in ("PRODUCT_INACTIVE", "PRICE_NOT_AVAILABLE") else "warning"
                found.append(Warning(change["code"], severity, change["message"]))

        if order.created_offline and order.hold_reason:
            found.append(Warning("OFFLINE_DATA_CHANGED", "warning", order.hold_reason))

        if order.ai_extraction is not None:
            for ai_item in order.ai_extraction.items:
                if ai_item.requires_clarification or ai_item.confidence < low_confidence:
                    found.append(Warning(
                        "AI_MATCH_UNCERTAIN", "warning",
                        f"“{ai_item.original_text}” was read as {ai_item.extracted_name} with "
                        f"{ai_item.confidence * 100:.0f}% confidence"
                        + ("; the customer had to clarify it" if ai_item.requires_clarification else ""),
                    ))

        signature = _signature(order)
        for other in nearby:
            if (other.id != order.id and other.retailer_id == order.retailer_id
                    and abs(other.created_at - order.created_at) <= window
                    and _signature(other) == signature):
                found.append(Warning("POSSIBLE_DUPLICATE", "warning",
                                     f"Same items as order {other.order_number} for this shop "
                                     f"({other.created_at.astimezone(IST):%d %b %H:%M}, {other.status})"))
    return result


def _q(value: Decimal) -> str:
    return f"{value.normalize():f}"


# ---------------------------------------------------------------- lists and review


def list_orders(
    db: Session, actor: User, *, view: str, statuses: Sequence[OrderStatus], source: OrderSource | None,
    search: str | None, salesman_id: uuid.UUID | None, from_date: date | None, to_date: date | None,
    exported: bool | None, sort: str, page: int, limit: int, retailer_id: uuid.UUID | None = None,
) -> tuple[list[DeskRow], int]:
    """One section of the Order Desk. Dates are IST days of placement (of confirmation in
    the confirmed section). `statuses` narrows the section's statuses."""
    ensure_role(actor, *ORDER_DESK_ROLES)
    if view not in VIEWS:
        raise AppException(f"Unknown view '{view}'", ErrorCode.VALIDATION_ERROR, 422, {"views": list(VIEWS)})
    if sort not in SORTS:
        raise AppException(f"Unknown sort '{sort}'", ErrorCode.VALIDATION_ERROR, 422, {"sorts": list(SORTS)})
    allowed = VIEWS[view]
    chosen = [s for s in statuses if not allowed or s in allowed] if statuses else list(allowed)
    if statuses and not chosen:
        return [], 0
    start, end = _ist_range(from_date, to_date)
    orders, total = repository.search_orders(
        db, statuses=chosen, source=source, search=(search or "").strip() or None, salesman_id=salesman_id,
        date_column=Order.approved_at if view == "confirmed" else Order.created_at, start=start, end=end,
        exported=exported, order_by=SORTS[sort], offset=(page - 1) * limit, limit=limit, retailer_id=retailer_id,
    )
    warnings = _warnings(db, orders)
    events = repository.last_events(db, [o.id for o in orders])
    return [DeskRow(o, salesman_of(o), warnings[o.id], events.get(o.id)) for o in orders], total


def review(db: Session, actor: User, order_id: uuid.UUID) -> Review:
    """Everything the desk needs to decide on one order."""
    ensure_role(actor, *ORDER_DESK_ROLES)
    order = repository.get_order(db, order_id)
    if order is None:
        raise AppException("Order not found", ErrorCode.RESOURCE_NOT_FOUND, 404, {"id": str(order_id)})
    account = retailer_repository.get_credit_account(db, order.retailer_id)
    stock = inventory_repository.get_stock(db, {i.product_id for i in order.items})
    needed: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    for item in order.items:
        needed[item.product_id] += item.paid_quantity + item.free_quantity
    return Review(
        order=order,
        salesman=salesman_of(order),
        credit=credit_summary(db, account) if account else None,
        stock=[LineStock(i.id, needed[i.product_id], stock.get(i.product_id, Decimal(0))) for i in order.items],
        warnings=_warnings(db, [order])[order.id],
        events=repository.events_for(db, order.id),
    )


def overview(db: Session, actor: User) -> dict:
    """Counts for the Order Desk overview cards (today = IST day)."""
    ensure_role(actor, *ORDER_DESK_ROLES)
    start, end = _today()
    counts = repository.count_by_status(db)
    open_orders = repository.orders_with_statuses(db, OPEN)
    warnings = _warnings(db, open_orders, with_prices=False)
    issues = [o for o in open_orders
              if any(w.code in ("INSUFFICIENT_STOCK", "CREDIT_LIMIT_EXCEEDED") for w in warnings[o.id])]
    return {
        "received_today": repository.count_created_between(db, start, end),
        "pending_review": sum(counts.get(s, 0) for s in VIEWS["incoming"]),
        "awaiting_clarification": counts.get(OrderStatus.CLARIFICATION_REQUIRED, 0),
        "confirmed_today": repository.count_status_between(db, OrderStatus.APPROVED, Order.approved_at, start, end),
        "confirmed_total": counts.get(OrderStatus.APPROVED, 0),
        "rejected_today": repository.count_events_between(db, OrderEventAction.REJECTED, start, end),
        "rejected_total": counts.get(OrderStatus.REJECTED, 0),
        "with_stock_or_credit_issues": len(issues),
        "not_exported": repository.count_not_exported(db),
    }


def status_counts(db: Session, actor: User) -> dict[str, int]:
    ensure_role(actor, *ORDER_DESK_ROLES)
    counts = repository.count_by_status(db)
    return {status.value: counts.get(status.value, 0) for status in OrderStatus}


def salesmen(db: Session, actor: User) -> list[User]:
    ensure_role(actor, *ORDER_DESK_ROLES)
    return repository.salesmen(db)


# ---------------------------------------------------------------- dispatch


@dataclass
class ProductTotal:
    product_id: uuid.UUID
    sku: str
    name: str
    pack_size: str
    order_unit: str
    paid: Decimal = Decimal(0)
    free: Decimal = Decimal(0)
    orders: int = 0

    @property
    def total(self) -> Decimal:
        return self.paid + self.free


@dataclass
class Stop:
    """One shop on the loading list: its confirmed orders and their combined quantities."""

    orders: list[Order]
    products: list[ProductTotal]

    @property
    def retailer(self):
        return self.orders[0].retailer


@dataclass
class Beat:
    salesman: User | None
    orders: list[Order]
    products: list[ProductTotal]
    stops: list[Stop]


@dataclass
class Dispatch:
    orders: list[Order]
    products: list[ProductTotal]
    beats: list[Beat]


def _consolidate(orders: Sequence[Order]) -> list[ProductTotal]:
    totals: dict[uuid.UUID, ProductTotal] = {}
    for order in orders:
        for item in order.items:
            row = totals.get(item.product_id)
            if row is None:
                row = totals[item.product_id] = ProductTotal(
                    item.product_id, item.sku, item.product_name, item.product.pack_size, item.product.order_unit)
            row.paid += item.paid_quantity
            row.free += item.free_quantity
            row.orders += 1
    return sorted(totals.values(), key=lambda r: (r.name, r.sku))


def _stops(orders: Sequence[Order]) -> list[Stop]:
    by_shop: dict[uuid.UUID, list[Order]] = defaultdict(list)
    for order in orders:
        by_shop[order.retailer_id].append(order)
    stops = [Stop(shop_orders, _consolidate(shop_orders)) for shop_orders in by_shop.values()]
    return sorted(stops, key=lambda s: s.retailer.shop_name)


def dispatch(db: Session, actor: User, from_date: date | None, to_date: date | None,
             salesman_id: uuid.UUID | None) -> Dispatch:
    """Confirmed orders (by IST confirmation day; default today) with consolidated product
    quantities (paid + free cases), overall and per salesman beat: the loading list. Routes
    and vans are not recorded in V1, so the salesman's beat is the grouping."""
    ensure_role(actor, *ORDER_DESK_ROLES)
    if from_date is None and to_date is None:
        from_date = to_date = datetime.now(IST).date()
    start, end = _ist_range(from_date, to_date)
    orders = repository.approved_between(db, start, end, salesman_id)
    by_salesman: dict[uuid.UUID | None, list[Order]] = defaultdict(list)
    people: dict[uuid.UUID | None, User | None] = {}
    for order in orders:
        person = salesman_of(order)
        key = person.id if person else None
        by_salesman[key].append(order)
        people[key] = person
    beats = [Beat(people[k], v, _consolidate(v), _stops(v)) for k, v in by_salesman.items()]
    beats.sort(key=lambda b: (b.salesman is None, b.salesman.name if b.salesman else ""))
    return Dispatch(orders, _consolidate(orders), beats)
