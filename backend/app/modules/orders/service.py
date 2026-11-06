"""Order workflow: creation, Order Desk review/correction, approval and rejection.

Every public function takes the acting user and enforces role and retailer access itself.
Functions that change data commit on success and roll back on any failure.
"""

import logging
import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import (
    OPEN_ORDER_STATUSES,
    ORDER_DESK_ROLES,
    CreditTransactionType,
    ErrorCode,
    OrderEventAction,
    OrderSource,
    OrderStatus,
    StockMovementType,
    UserRole,
)
from app.core.permissions import ensure_can_access_retailer, ensure_role, forbidden, visible_retailer_ids
from app.exceptions.base import AppException
from app.models import (
    CreditLedger,
    Order,
    OrderCorrection,
    OrderEvent,
    OrderItem,
    Product,
    Retailer,
    Scheme,
    StockMovement,
    User,
)
from app.modules.ai_orders import repository as ai_repository
from app.modules.inventory import repository as inventory_repository
from app.modules.orders import repository
from app.modules.orders.schemas import CorrectOrderItemInput, CreateOrderInput, OrderItemInput
from app.modules.pricing import service as pricing
from app.modules.schemes import engine as schemes_engine
from app.modules.retailers import repository as retailer_repository
from app.modules.retailers.service import credit_available, get_retailer_for

logger = logging.getLogger(__name__)

ORDERING_ROLES = (UserRole.RETAILER, UserRole.SALESMAN)
IST = ZoneInfo("Asia/Kolkata")


# ---------------------------------------------------------------- helpers


def _not_found(what: str, identifier: uuid.UUID) -> AppException:
    return AppException(f"{what} not found", ErrorCode.RESOURCE_NOT_FOUND, 404, {"id": str(identifier)})


def _new_order_number(now: datetime) -> str:
    """DF-<date in India>-<random>, e.g. DF-20261104-1A2B3C4D."""
    return f"DF-{now.astimezone(IST):%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"


def _load_products(db: Session, product_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, Product]:
    products = repository.get_products(db, product_ids)
    missing = [str(pid) for pid in product_ids if pid not in products or not products[pid].is_active]
    if missing:
        raise AppException(
            "Product not found or inactive", ErrorCode.PRODUCT_NOT_FOUND, 404, {"product_ids": missing}
        )
    return products


def _ensure_order_unit(product: Product, unit: str) -> None:
    """V1 orders are placed in the product's order unit. Any other unit is refused rather
    than converted, so the system never guesses whether a quantity meant cases or pieces."""
    if unit.strip().casefold() != product.order_unit.casefold():
        raise AppException(
            f"{product.sku} is ordered in {product.order_unit}s; quantity was given in '{unit}'",
            ErrorCode.VALIDATION_ERROR,
            422,
            {"sku": product.sku, "order_unit": product.order_unit, "unit": unit},
        )


def _ensure_unique_products(product_ids: Sequence[uuid.UUID]) -> None:
    if len(set(product_ids)) != len(product_ids):
        raise AppException(
            "Each product may appear only once per order", ErrorCode.VALIDATION_ERROR, 422
        )


def _stock_shortages(
    db: Session, needed: dict[uuid.UUID, Decimal], products: dict[uuid.UUID, Product]
) -> list[dict]:
    stock = inventory_repository.get_stock(db, needed.keys())
    return [
        {"sku": products[pid].sku, "required": str(qty), "available": str(stock.get(pid, Decimal(0)))}
        for pid, qty in needed.items()
        if qty > stock.get(pid, Decimal(0))
    ]


def _ensure_stock_available(
    db: Session, needed: dict[uuid.UUID, Decimal], products: dict[uuid.UUID, Product]
) -> None:
    """Pre-submission stock validation (paid + free cases). Approval re-checks under lock."""
    shortages = _stock_shortages(db, needed, products)
    if shortages:
        raise AppException("Insufficient stock", ErrorCode.INSUFFICIENT_STOCK, 409, {"items": shortages})


def _apply_line(item: OrderItem, product: Product, line: pricing.LineAmounts) -> None:
    item.product_id = product.id
    item.product_name = product.name
    item.sku = product.sku
    item.paid_quantity = line.paid_quantity
    item.free_quantity = line.free_quantity
    item.price_basis = line.price_basis
    item.unit_price = line.unit_price
    item.discount_percentage = line.discount_percentage
    item.discount_amount = line.discount_amount
    item.gst_rate = line.gst_rate
    item.tax_inclusive = line.tax_inclusive
    item.scheme_id = line.scheme_id
    item.scheme_snapshot = line.scheme.snapshot() if line.scheme else None
    item.taxable_amount = line.taxable_amount
    item.gst_amount = line.gst_amount
    item.line_total = line.line_total


def _apply_totals(order: Order, totals: pricing.OrderTotals) -> None:
    order.subtotal = totals.subtotal
    order.discount_total = totals.discount_total
    order.taxable_amount = totals.taxable_amount
    order.gst_amount = totals.gst_amount
    order.grand_total = totals.grand_total


def _credit_status(
    db: Session, retailer_id: uuid.UUID, grand_total: Decimal, exclude_order_id: uuid.UUID | None = None
) -> OrderStatus:
    available = credit_available(db, retailer_id, exclude_order_id)
    return OrderStatus.CREDIT_HOLD if grand_total > available else OrderStatus.PENDING


CREDIT_CONTACT = "Please contact your salesman or the distributor's order desk."


def _ensure_retailer_within_credit(db: Session, actor: User, retailer_id: uuid.UUID, grand_total: Decimal) -> None:
    """Retailers cannot place an order above their available credit (credit_limit -
    current_outstanding - credit held by their orders under review). Salesman orders above it
    still go to CREDIT_HOLD for the Order Desk."""
    if actor.role != UserRole.RETAILER:
        return
    available = credit_available(db, retailer_id)
    if grand_total > available:
        message = (
            "Your credit limit has been reached." if available <= 0
            else f"This order (Rs {grand_total:,.2f}) is more than your available credit (Rs {available:,.2f})."
        )
        raise AppException(
            f"{message} {CREDIT_CONTACT}",
            ErrorCode.CREDIT_LIMIT_EXCEEDED,
            409,
            {"grand_total": str(grand_total), "available_credit": str(available)},
        )


def record_event(
    db: Session, order: Order, action: OrderEventAction, actor: User | None,
    message: str | None = None, details: dict | None = None,
) -> None:
    """Append to the order's history (order_events)."""
    db.add(OrderEvent(order_id=order.id, action=action, actor_id=actor.id if actor else None,
                      message=message, details=details, created_at=datetime.now(UTC)))


def current_changes(db: Session, order: Order) -> list[dict]:
    """What changed for this order's lines since it was placed: inactive products, and
    current dealer price or scheme benefit (for the same quantity) different from the
    line's snapshot. The order itself keeps its placement prices; this is for the desk."""
    changes: list[dict] = []
    now = datetime.now(UTC)
    for item in order.items:
        product = item.product
        if not product.is_active:
            changes.append({"code": "PRODUCT_INACTIVE", "sku": item.sku,
                            "message": f"{item.sku}: product is no longer active"})
            continue
        try:
            [line] = pricing.price_lines(db, order.retailer_id, [(product, item.paid_quantity)], now)
        except AppException as exc:
            changes.append({"code": "PRICE_NOT_AVAILABLE", "sku": item.sku,
                            "message": f"{item.sku}: {exc.message}"})
            continue
        if line.unit_price != item.unit_price:
            changes.append({"code": "PRICE_CHANGED", "sku": item.sku,
                            "message": f"{item.sku}: dealer price is now Rs {line.unit_price} "
                                       f"(Rs {item.unit_price} on the order)"})
        before = (item.scheme_id, item.free_quantity, item.discount_percentage) if item.scheme_id else None
        after = (line.scheme_id, line.free_quantity, line.discount_percentage) if line.scheme else None
        if before != after:
            was = (item.scheme_snapshot or {}).get("description", "no scheme")
            now_text = line.scheme.description if line.scheme else "no scheme"
            changes.append({"code": "SCHEME_CHANGED", "sku": item.sku,
                            "message": f"{item.sku}: scheme is now {now_text} ({was} on the order)"})
    return changes


def _ensure_open(order: Order) -> None:
    if order.status not in OPEN_ORDER_STATUSES:
        raise AppException(
            f"Order is {order.status}; only open (PENDING, CREDIT_HOLD, ON_HOLD or "
            "CLARIFICATION_REQUIRED) orders can be changed",
            ErrorCode.INVALID_ORDER_STATUS,
            409,
            {"status": order.status},
        )


# ---------------------------------------------------------------- creation


def resolve_ordering_retailer(db: Session, actor: User, retailer_id: uuid.UUID | None) -> Retailer:
    """Retailers order for their own shop; salesmen only for their assigned retailers."""
    ensure_role(actor, *ORDERING_ROLES)
    if actor.role == UserRole.RETAILER:
        if retailer_id is not None and retailer_id != actor.retailer_id:
            raise forbidden("Retailers can only place orders for their own shop")
        retailer_id = actor.retailer_id
    if retailer_id is None:
        raise AppException("retailer_id is required", ErrorCode.VALIDATION_ERROR, 422)
    return get_retailer_for(db, actor, retailer_id)


def _price_items(
    db: Session, retailer: Retailer, items: Sequence[OrderItemInput], at: datetime
) -> tuple[dict[uuid.UUID, Product], list[pricing.LineAmounts]]:
    """Validate products/units and price each line for the retailer at `at`."""
    product_ids = [item.product_id for item in items]
    _ensure_unique_products(product_ids)
    products = _load_products(db, product_ids)
    for item in items:
        _ensure_order_unit(products[item.product_id], item.unit)
    lines = pricing.price_lines(
        db, retailer.id, [(products[item.product_id], item.quantity) for item in items], at
    )
    return products, lines


@dataclass(frozen=True)
class QuoteLine:
    product: Product
    line: pricing.LineAmounts
    available_stock: Decimal

    @property
    def stock_ok(self) -> bool:
        return self.line.paid_quantity + self.line.free_quantity <= self.available_stock


@dataclass(frozen=True)
class Quote:
    lines: list[QuoteLine]
    totals: pricing.OrderTotals
    available_credit: Decimal
    ordering_restricted_reason: str | None = None

    @property
    def within_credit(self) -> bool:
        return self.totals.grand_total <= self.available_credit

    @property
    def can_order(self) -> bool:
        return all(line.stock_ok for line in self.lines)


def quote_order(db: Session, actor: User, data: CreateOrderInput) -> Quote:
    """Cart preview: the same pricing, schemes and stock check as order creation, without
    saving anything. Stock shortages are reported per line, and whether the total fits the
    retailer's available credit is reported instead of refusing."""
    retailer = resolve_ordering_retailer(db, actor, data.retailer_id)
    products, lines = _price_items(db, retailer, data.items, datetime.now(UTC))
    stock = inventory_repository.get_stock(db, products.keys())
    return Quote(
        lines=[
            QuoteLine(products[item.product_id], line, stock.get(item.product_id, Decimal(0)))
            for item, line in zip(data.items, lines)
        ],
        totals=pricing.calculate_totals(lines),
        available_credit=credit_available(db, retailer.id),
        ordering_restricted_reason=retailer.ordering_restricted_reason,
    )


def ensure_ordering_allowed(retailer: Retailer) -> None:
    """The Admin can stop new orders for a retailer (all channels) until the restriction is removed."""
    if not retailer.is_active:
        raise AppException("This retailer is inactive and cannot place orders", ErrorCode.ORDERING_RESTRICTED, 403)
    if retailer.ordering_restricted_reason:
        raise AppException(
            f"Ordering is paused for this shop: {retailer.ordering_restricted_reason}. {CREDIT_CONTACT}",
            ErrorCode.ORDERING_RESTRICTED, 403, {"reason": retailer.ordering_restricted_reason},
        )


def build_order(
    db: Session,
    actor: User,
    retailer: Retailer,
    items: Sequence[OrderItemInput],
    *,
    source: OrderSource,
    remarks: str | None = None,
    ai_extraction_id: uuid.UUID | None = None,
    sync: CreateOrderInput | None = None,
) -> Order:
    """Price, validate and add a new order to the session (caller commits).

    Prices, schemes, GST and totals are always calculated here from the database;
    nothing price-related is accepted from the caller.

    Offline orders synced later (`sync.created_offline`) are never refused or silently
    changed because data moved on while the device was offline: a price that differs from
    what the device showed, or a stock shortage, puts the order ON_HOLD with the reasons
    for the Order Desk.
    """
    ensure_ordering_allowed(retailer)
    now = datetime.now(UTC)
    products, lines = _price_items(db, retailer, items, now)
    product_ids = [item.product_id for item in items]
    needed = {pid: line.paid_quantity + line.free_quantity for pid, line in zip(product_ids, lines)}
    review: list[str] = []
    if sync is not None and sync.created_offline:
        for shortage in _stock_shortages(db, needed, products):
            review.append(f"{shortage['sku']}: {_qty(shortage['required'])} cases needed (incl. free), "
                          f"{_qty(shortage['available'])} in stock")
    else:
        _ensure_stock_available(db, needed, products)
    for item, line in zip(items, lines):
        if item.expected_unit_price is not None and item.expected_unit_price != line.unit_price:
            review.append(f"{products[item.product_id].sku}: price changed from Rs {item.expected_unit_price} "
                          f"to Rs {line.unit_price} since the salesman's last sync")
    for item, line in zip(items, lines):
        # Only a different benefit for this quantity matters (a scheme that would not have
        # applied anyway, e.g. "5+ cases" on a 2-case line, is not a change for this order).
        if item.expected_scheme_ids is None:
            continue
        shown = [s for s in (db.get(Scheme, sid) for sid in item.expected_scheme_ids) if s is not None]
        try:
            expected = schemes_engine.evaluate(item.quantity, shown)
        except AppException:
            expected = None  # the phone's own data was conflicting: compare with "no scheme"
        before = (expected.scheme_id, expected.free_quantity, expected.discount_percentage) if expected else None
        after = (line.scheme_id, line.free_quantity, line.discount_percentage) if line.scheme else None
        if before != after:
            review.append(
                f"{products[item.product_id].sku}: scheme changed since the salesman's last sync "
                f"({expected.description if expected else 'no scheme'} when ordered, "
                f"{line.scheme.description if line.scheme else 'no scheme'} now)"
            )

    totals = pricing.calculate_totals(lines)
    _ensure_retailer_within_credit(db, actor, retailer.id, totals.grand_total)
    status = _credit_status(db, retailer.id, totals.grand_total)
    if review:
        if status == OrderStatus.CREDIT_HOLD:
            review.append("the order is also above the retailer's available credit")
        status = OrderStatus.ON_HOLD
    order = Order(
        order_number=_new_order_number(now),
        retailer_id=retailer.id,
        created_by=actor.id,
        ai_extraction_id=ai_extraction_id,
        source=source,
        status=status,
        hold_reason=("Offline order needs review: " + "; ".join(review)) if review else None,
        remarks=remarks,
        client_order_id=sync.client_order_id if sync else None,
        created_offline=bool(sync and sync.created_offline),
        client_created_at=sync.client_created_at if sync else None,
    )
    _apply_totals(order, totals)
    for product_id, line in zip(product_ids, lines):
        item = OrderItem()
        _apply_line(item, products[product_id], line)
        order.items.append(item)
    db.add(order)
    db.flush()
    record_event(db, order, OrderEventAction.RECEIVED, actor, order.hold_reason, {
        "source": source, "status": status, "created_offline": order.created_offline,
        "grand_total": str(order.grand_total),
    })
    return order


def create_order(db: Session, actor: User, data: CreateOrderInput) -> Order:
    """Manual order by a retailer (source MANUAL) or a salesman (source SALESMAN).

    Like AI orders, it waits for the Order Desk, which accepts (stock deducted, credit
    debited) or rejects it. While it waits it holds its total from the retailer's available
    credit. A salesman order above the available credit arrives as CREDIT_HOLD.
    """
    if data.client_order_id:
        existing = _existing_client_order(db, actor, data.client_order_id)
        if existing is not None:
            return existing  # a retried sync: same order, never a duplicate
    try:
        retailer = resolve_ordering_retailer(db, actor, data.retailer_id)
        source = OrderSource.SALESMAN if actor.role == UserRole.SALESMAN else OrderSource.MANUAL
        order = build_order(db, actor, retailer, data.items, source=source, remarks=data.remarks, sync=data)
        db.commit()
        return order
    except IntegrityError:
        # Two copies of the same device order arrived at once: the other one won.
        db.rollback()
        existing = _existing_client_order(db, actor, data.client_order_id) if data.client_order_id else None
        if existing is None:
            raise
        return existing
    except AppException as exc:
        db.rollback()
        if data.client_order_id and actor.role == UserRole.SALESMAN:
            _record_sync_failure(db, actor, data, exc)
        raise
    except Exception:
        db.rollback()
        raise


def _record_sync_failure(db: Session, actor: User, data: CreateOrderInput, exc: AppException) -> None:
    """A salesman's device order the server refused (the phone shows it as "Sync failed").
    Kept in the audit log so the Admin can see why; the order itself stays on the phone."""
    from app.modules.audit.service import record

    try:
        record(db, actor, "SYNC_FAILED", "order_sync", data.client_order_id, data.client_order_id, {
            "error_code": exc.error_code, "message": exc.message, "retailer_id": data.retailer_id,
            "created_offline": data.created_offline, "client_created_at": data.client_created_at,
            "items": [{"product_id": i.product_id, "quantity": i.quantity} for i in data.items],
        })
        db.commit()
    except Exception as log_error:  # never hide the original error, but do not lose this silently
        db.rollback()
        logger.warning("Could not record a failed salesman sync (%s) for device order %s",
                       type(log_error).__name__, data.client_order_id)


def _existing_client_order(db: Session, actor: User, client_order_id: str) -> Order | None:
    existing = repository.get_order_by_client_id(db, client_order_id)
    if existing is not None and existing.created_by != actor.id:
        raise AppException("This order id is already used", ErrorCode.VALIDATION_ERROR, 409,
                           {"client_order_id": client_order_id})
    return existing


def _qty(value: str) -> str:
    return f"{Decimal(value).normalize():f}"


# ---------------------------------------------------------------- reading


def get_order(db: Session, actor: User, order_id: uuid.UUID) -> Order:
    order = repository.get_order(db, order_id)
    if order is None:
        raise _not_found("Order", order_id)
    ensure_can_access_retailer(actor, order.retailer)
    return order


def _visible_retailers(db: Session, actor: User) -> list[uuid.UUID] | None:
    assigned = (
        retailer_repository.get_assigned_retailer_ids(db, actor.id)
        if actor.role == UserRole.SALESMAN
        else []
    )
    return visible_retailer_ids(actor, assigned)


def list_orders(db: Session, actor: User, status: OrderStatus | None = None) -> list[Order]:
    return repository.list_orders(db, _visible_retailers(db, actor), status)


def search_orders(
    db: Session,
    actor: User,
    *,
    statuses: Sequence[OrderStatus] = (),
    source: OrderSource | None = None,
    search: str | None = None,
    page: int = 1,
    limit: int = 20,
    created_by_me: bool = False,
    retailer_id: uuid.UUID | None = None,
) -> tuple[list[Order], int]:
    """Paginated order list, limited to the retailers the actor may see.
    `search` matches the order number or the retailer's shop name; `created_by_me` keeps the
    orders the actor placed (salesman history); `retailer_id` one visible retailer."""
    if retailer_id is not None:
        get_retailer_for(db, actor, retailer_id)  # 403 if not visible to the actor
    return repository.search_orders(
        db, _visible_retailers(db, actor), list(statuses), source,
        (search or "").strip() or None, (page - 1) * limit, limit,
        created_by=actor.id if created_by_me else None, retailer_id=retailer_id,
    )


# ---------------------------------------------------------------- Order Desk


def correct_order_item(
    db: Session, actor: User, order_id: uuid.UUID, item_id: uuid.UUID, data: CorrectOrderItemInput
) -> OrderCorrection:
    """Order Desk correction of an item's product and/or quantity before approval.

    The line is re-priced with the prices and schemes that were effective when the order
    was placed, totals and credit status are recalculated, and the change is recorded in
    order_corrections. Optionally the retailer's wording is saved as an alias.
    """
    ensure_role(actor, *ORDER_DESK_ROLES)
    try:
        order = repository.get_order(db, order_id, lock=True)
        if order is None:
            raise _not_found("Order", order_id)
        _ensure_open(order)
        item = next((i for i in order.items if i.id == item_id), None)
        if item is None:
            raise _not_found("Order item", item_id)

        if not data.reason.strip():
            raise AppException("A correction reason is required", ErrorCode.VALIDATION_ERROR, 422)
        new_product_id = data.new_product_id or item.product_id
        new_quantity = data.new_quantity or item.paid_quantity
        if new_product_id == item.product_id and new_quantity == item.paid_quantity:
            raise AppException("The correction does not change anything", ErrorCode.VALIDATION_ERROR, 422)
        if any(other.product_id == new_product_id for other in order.items if other.id != item.id):
            raise AppException(
                "That product is already on this order; correct that line instead",
                ErrorCode.VALIDATION_ERROR,
                422,
            )

        product = _load_products(db, [new_product_id])[new_product_id]
        if data.unit is not None:
            _ensure_order_unit(product, data.unit)
        [line] = pricing.price_lines(db, order.retailer_id, [(product, new_quantity)], order.created_at)
        _ensure_stock_available(db, {product.id: line.paid_quantity + line.free_quantity}, {product.id: product})

        old = {"sku": item.sku, "name": item.product_name, "quantity": str(item.paid_quantity),
               "line_total": str(item.line_total), "order_total": str(order.grand_total)}
        correction = OrderCorrection(
            order_item_id=item.id,
            old_product_id=item.product_id,
            new_product_id=product.id,
            old_quantity=item.paid_quantity,
            new_quantity=new_quantity,
            corrected_by=actor.id,
            reason=data.reason.strip(),
        )
        db.add(correction)
        _apply_line(item, product, line)
        _apply_totals(order, pricing.calculate_totals(order.items))
        # A hold or a clarification request stays until the desk acts on it.
        if order.status not in (OrderStatus.ON_HOLD, OrderStatus.CLARIFICATION_REQUIRED):
            order.status = _credit_status(db, order.retailer_id, order.grand_total, exclude_order_id=order.id)
        record_event(db, order, OrderEventAction.CORRECTED, actor, data.reason.strip(), {
            "old": old,
            "new": {"sku": item.sku, "name": item.product_name, "quantity": str(item.paid_quantity),
                    "line_total": str(item.line_total), "order_total": str(order.grand_total)},
        })

        if data.save_alias and data.save_alias.strip():
            ai_repository.save_alias(db, order.retailer_id, product.id, data.save_alias.strip())
        elif order.ai_extraction_id and product.id != correction.old_product_id:
            # Learning loop: the Order Desk says these words of this retailer mean this product.
            from app.modules.ai_orders.matcher import wording_for_alias

            ai_line = ai_repository.extraction_item_for_order_item(db, item.id)
            wording = wording_for_alias(ai_line.original_text, ai_line.quantity) if ai_line else ""
            if wording:
                ai_repository.save_alias(db, order.retailer_id, product.id, wording)

        db.commit()
        return correction
    except Exception:
        db.rollback()
        raise


def _confirm(db: Session, actor: User, order: Order, override_reason: str | None, *, reason: str) -> None:
    """Confirm an open order (DATABASE_DESIGN.MD section 7), without committing.

    Locks its inventory rows and the retailer's credit account; rechecks stock (paid + free)
    and credit (other open orders keep holding theirs); verifies totals; deducts stock with
    stock movements; debits credit with a ledger entry; marks the order APPROVED. Raises
    CREDIT_LIMIT_EXCEEDED above available credit unless an override reason is given.
    """
    # 1-2. Lock inventory rows and recheck stock including free quantities.
    needed: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    for item in order.items:
        needed[item.product_id] += item.paid_quantity + item.free_quantity
    inventory = inventory_repository.lock_inventory(db, needed.keys())
    shortages = [
        {"product_id": str(pid), "required": str(qty),
         "available": str(inventory[pid].stock_cases if pid in inventory else Decimal(0))}
        for pid, qty in needed.items()
        if pid not in inventory or inventory[pid].stock_cases < qty
    ]
    if shortages:
        raise AppException("Insufficient stock", ErrorCode.INSUFFICIENT_STOCK, 409, {"items": shortages})

    # 3. Recheck available credit (locked so concurrent confirmations see each other's debits).
    account = retailer_repository.get_credit_account(db, order.retailer_id, lock=True)
    if account is None:
        raise AppException("Retailer has no credit account", ErrorCode.RESOURCE_NOT_FOUND, 404)
    available = credit_available(db, order.retailer_id, exclude_order_id=order.id, account=account)
    if order.grand_total > available and override_reason is None:
        raise AppException(
            "Order exceeds the retailer's available credit",
            ErrorCode.CREDIT_LIMIT_EXCEEDED,
            409,
            {"grand_total": str(order.grand_total), "available_credit": str(available)},
        )

    # 4. Verify the stored totals still equal the sum of the line snapshots.
    totals = pricing.calculate_totals(order.items)
    if (order.subtotal, order.discount_total, order.taxable_amount, order.gst_amount,
            order.grand_total) != (totals.subtotal, totals.discount_total,
                                   totals.taxable_amount, totals.gst_amount, totals.grand_total):
        raise AppException("Order totals do not match its items", ErrorCode.INTERNAL_SERVER_ERROR, 500)

    # 5-6. Deduct stock and record movements (negative = stock leaves the warehouse).
    for product_id, quantity in needed.items():
        inventory[product_id].stock_cases -= quantity
        inventory_repository.add_movement(db, StockMovement(
            product_id=product_id,
            order_id=order.id,
            movement_type=StockMovementType.ORDER_DEDUCTION,
            quantity=-quantity,
            stock_after=inventory[product_id].stock_cases,
            reference=f"Order {order.order_number}",
            created_by=actor.id,
        ))

    # 7. Debit the retailer's credit (V1 policy: the full grand total on confirmation).
    account.current_outstanding += order.grand_total
    description = f"Order {order.order_number} {reason}"
    if order.grand_total > available:
        description += f"; credit limit exceeded, released by Order Desk: {override_reason}"
    retailer_repository.add_ledger_entry(db, CreditLedger(
        retailer_id=order.retailer_id,
        order_id=order.id,
        transaction_type=CreditTransactionType.ORDER_DEBIT,
        amount=order.grand_total,
        description=description,
        created_by=actor.id,
    ))

    # 8. Mark approved and record it (the caller commits).
    order.status = OrderStatus.APPROVED
    order.approved_by = actor.id
    order.approved_at = datetime.now(UTC)
    record_event(db, order, OrderEventAction.CONFIRMED, actor,
                 override_reason if order.grand_total > available else None,
                 {"reason": reason, "grand_total": str(order.grand_total),
                  "credit_override": order.grand_total > available})


def approve_order(
    db: Session, actor: User, order_id: uuid.UUID, credit_override_reason: str | None = None,
    acknowledge_changes: bool = False,
) -> Order:
    """Order Desk confirmation of an open order (AI-captured, or a credit/manual hold), in one
    transaction. Any failure rolls back everything.

    Stock and credit are rechecked under lock. A product that is no longer active blocks the
    confirmation; a dealer price or scheme that changed since the order was placed is never
    applied silently: the desk must confirm with acknowledge_changes (the order keeps its
    placement prices) or correct the line first (ORDER_DATA_CHANGED otherwise).

    If the order exceeds available credit, approval needs a credit_override_reason (Order
    Desk releasing a credit hold); without one the order is left on CREDIT_HOLD.
    """
    ensure_role(actor, *ORDER_DESK_ROLES)
    override_reason = (credit_override_reason or "").strip() or None
    credit_refused = False
    try:
        order = repository.get_order(db, order_id, lock=True)
        if order is None:
            raise _not_found("Order", order_id)
        _ensure_open(order)
        changes = current_changes(db, order)
        inactive = [c for c in changes if c["code"] == "PRODUCT_INACTIVE"]
        if inactive:
            raise AppException("A product on this order is no longer active; correct that line first",
                               ErrorCode.PRODUCT_NOT_FOUND, 409, {"changes": inactive})
        if changes and not acknowledge_changes:
            raise AppException(
                "Prices or schemes changed since this order was placed. Review the changes, then "
                "confirm at the order's prices or correct the lines.",
                ErrorCode.ORDER_DATA_CHANGED, 409, {"changes": changes},
            )
        try:
            _confirm(db, actor, order, override_reason, reason="approved")
        except AppException as exc:
            credit_refused = exc.error_code == ErrorCode.CREDIT_LIMIT_EXCEEDED
            raise
        db.commit()
        return order
    except Exception:
        db.rollback()
        if credit_refused:
            _place_on_credit_hold(db, actor, order_id)
        raise


def _place_on_credit_hold(db: Session, actor: User, order_id: uuid.UUID) -> None:
    """After a refused approval, keep a PENDING order visible as CREDIT_HOLD."""
    order = repository.get_order(db, order_id, lock=True)
    if order is not None and order.status == OrderStatus.PENDING:
        order.status = OrderStatus.CREDIT_HOLD
        record_event(db, order, OrderEventAction.CREDIT_HOLD, actor,
                     "Confirmation refused: above the retailer's available credit")
    db.commit()


def hold_order(db: Session, actor: User, order_id: uuid.UUID, reason: str) -> Order:
    """Order Desk puts an open order ON_HOLD with a reason (e.g. waiting for the retailer).
    It can still be corrected, approved or rejected later. No stock or credit changes."""
    ensure_role(actor, *ORDER_DESK_ROLES)
    if not reason or not reason.strip():
        raise AppException("A hold reason is required", ErrorCode.VALIDATION_ERROR, 422)
    try:
        order = repository.get_order(db, order_id, lock=True)
        if order is None:
            raise _not_found("Order", order_id)
        _ensure_open(order)
        order.status = OrderStatus.ON_HOLD
        order.hold_reason = reason.strip()
        record_event(db, order, OrderEventAction.PUT_ON_HOLD, actor, order.hold_reason)
        db.commit()
        return order
    except Exception:
        db.rollback()
        raise


def request_clarification(db: Session, actor: User, order_id: uuid.UUID, message: str) -> Order:
    """Order Desk asks the retailer/salesman about an open order (unclear product, quantity,
    price...). The order and its lines stay exactly as placed; it moves to
    CLARIFICATION_REQUIRED (still holding credit) until the desk corrects, confirms or rejects it."""
    ensure_role(actor, *ORDER_DESK_ROLES)
    if not message or not message.strip():
        raise AppException("A clarification message is required", ErrorCode.VALIDATION_ERROR, 422)
    try:
        order = repository.get_order(db, order_id, lock=True)
        if order is None:
            raise _not_found("Order", order_id)
        _ensure_open(order)
        order.status = OrderStatus.CLARIFICATION_REQUIRED
        order.clarification_message = message.strip()
        record_event(db, order, OrderEventAction.CLARIFICATION_REQUESTED, actor, order.clarification_message)
        db.commit()
        return order
    except Exception:
        db.rollback()
        raise


DEFAULT_REJECTION_REASON = "Rejected by the order desk"


def reject_order(db: Session, actor: User, order_id: uuid.UUID, reason: str | None = None) -> Order:
    """Reject (one click; the reason is optional and defaults to DEFAULT_REJECTION_REASON).
    No stock is deducted and no credit is debited; the order's credit hold is released."""
    ensure_role(actor, *ORDER_DESK_ROLES)
    reason = (reason or "").strip() or DEFAULT_REJECTION_REASON
    try:
        order = repository.get_order(db, order_id, lock=True)
        if order is None:
            raise _not_found("Order", order_id)
        _ensure_open(order)
        order.status = OrderStatus.REJECTED
        order.rejection_reason = reason.strip()
        record_event(db, order, OrderEventAction.REJECTED, actor, order.rejection_reason)
        db.commit()
        return order
    except Exception:
        db.rollback()
        raise
