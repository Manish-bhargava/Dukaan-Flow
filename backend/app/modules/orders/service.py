"""Order workflow: creation, Order Desk review/correction, approval and rejection.

Every public function takes the acting user and enforces role and retailer access itself.
Functions that change data commit on success and roll back on any failure.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.constants import (
    OPEN_ORDER_STATUSES,
    ORDER_DESK_ROLES,
    CreditTransactionType,
    ErrorCode,
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
    OrderItem,
    Product,
    Retailer,
    StockMovement,
    User,
)
from app.modules.ai_orders import repository as ai_repository
from app.modules.inventory import repository as inventory_repository
from app.modules.orders import repository
from app.modules.orders.schemas import CorrectOrderItemInput, CreateOrderInput, OrderItemInput
from app.modules.pricing import service as pricing
from app.modules.retailers import repository as retailer_repository
from app.modules.retailers.service import available_credit, get_retailer_for

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


def _ensure_stock_available(
    db: Session, needed: dict[uuid.UUID, Decimal], products: dict[uuid.UUID, Product]
) -> None:
    """Pre-submission stock validation (paid + free cases). Approval re-checks under lock."""
    stock = inventory_repository.get_stock(db, needed.keys())
    shortages = [
        {"sku": products[pid].sku, "required": str(qty), "available": str(stock.get(pid, Decimal(0)))}
        for pid, qty in needed.items()
        if qty > stock.get(pid, Decimal(0))
    ]
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


def _credit_status(db: Session, retailer_id: uuid.UUID, grand_total: Decimal) -> OrderStatus:
    account = retailer_repository.get_credit_account(db, retailer_id)
    return OrderStatus.CREDIT_HOLD if grand_total > available_credit(account) else OrderStatus.PENDING


def _ensure_open(order: Order) -> None:
    if order.status not in OPEN_ORDER_STATUSES:
        raise AppException(
            f"Order is {order.status}; only open (PENDING, CREDIT_HOLD or ON_HOLD) orders can be changed",
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

    @property
    def can_order(self) -> bool:
        return all(line.stock_ok for line in self.lines)


def quote_order(db: Session, actor: User, data: CreateOrderInput) -> Quote:
    """Cart preview: the same pricing, schemes and stock check as order creation, without
    saving anything. Stock shortages are reported per line instead of refusing."""
    retailer = resolve_ordering_retailer(db, actor, data.retailer_id)
    products, lines = _price_items(db, retailer, data.items, datetime.now(UTC))
    stock = inventory_repository.get_stock(db, products.keys())
    return Quote(
        lines=[
            QuoteLine(products[item.product_id], line, stock.get(item.product_id, Decimal(0)))
            for item, line in zip(data.items, lines)
        ],
        totals=pricing.calculate_totals(lines),
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
) -> Order:
    """Price, validate and add a new order to the session (caller commits).

    Prices, schemes, GST and totals are always calculated here from the database;
    nothing price-related is accepted from the caller.
    """
    now = datetime.now(UTC)
    products, lines = _price_items(db, retailer, items, now)
    product_ids = [item.product_id for item in items]
    _ensure_stock_available(
        db, {line_product: line.paid_quantity + line.free_quantity
             for line_product, line in zip(product_ids, lines)}, products
    )

    totals = pricing.calculate_totals(lines)
    order = Order(
        order_number=_new_order_number(now),
        retailer_id=retailer.id,
        created_by=actor.id,
        ai_extraction_id=ai_extraction_id,
        source=source,
        status=_credit_status(db, retailer.id, totals.grand_total),
        remarks=remarks,
    )
    _apply_totals(order, totals)
    for product_id, line in zip(product_ids, lines):
        item = OrderItem()
        _apply_line(item, products[product_id], line)
        order.items.append(item)
    db.add(order)
    db.flush()
    return order


def create_order(db: Session, actor: User, data: CreateOrderInput) -> Order:
    """Manual order by a retailer (source MANUAL) or a salesman (source SALESMAN)."""
    try:
        retailer = resolve_ordering_retailer(db, actor, data.retailer_id)
        source = OrderSource.SALESMAN if actor.role == UserRole.SALESMAN else OrderSource.MANUAL
        order = build_order(db, actor, retailer, data.items, source=source, remarks=data.remarks)
        db.commit()
        return order
    except Exception:
        db.rollback()
        raise


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
) -> tuple[list[Order], int]:
    """Paginated order list, limited to the retailers the actor may see.
    `search` matches the order number or the retailer's shop name."""
    return repository.search_orders(
        db, _visible_retailers(db, actor), list(statuses), source,
        (search or "").strip() or None, (page - 1) * limit, limit,
    )


def status_counts(db: Session, actor: User) -> dict[str, int]:
    ensure_role(actor, *ORDER_DESK_ROLES)
    counts = repository.count_by_status(db)
    return {status.value: counts.get(status.value, 0) for status in OrderStatus}


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

        correction = OrderCorrection(
            order_item_id=item.id,
            old_product_id=item.product_id,
            new_product_id=product.id,
            old_quantity=item.paid_quantity,
            new_quantity=new_quantity,
            corrected_by=actor.id,
            reason=data.reason,
        )
        db.add(correction)
        _apply_line(item, product, line)
        _apply_totals(order, pricing.calculate_totals(order.items))
        if order.status != OrderStatus.ON_HOLD:  # a manual hold stays until the desk acts
            order.status = _credit_status(db, order.retailer_id, order.grand_total)

        if data.save_alias and data.save_alias.strip():
            ai_repository.save_alias(db, order.retailer_id, product.id, data.save_alias.strip())

        db.commit()
        return correction
    except Exception:
        db.rollback()
        raise


def approve_order(
    db: Session, actor: User, order_id: uuid.UUID, credit_override_reason: str | None = None
) -> Order:
    """Approve an order in one transaction (DATABASE_DESIGN.MD section 7).

    Locks the order, its inventory rows and the retailer's credit account; rechecks stock
    (paid + free) and credit; verifies totals; deducts stock with stock movements; debits
    credit with a ledger entry; marks the order APPROVED. Any failure rolls back everything.

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

        # 3. Recheck available credit (locked so concurrent approvals see each other's debits).
        account = retailer_repository.get_credit_account(db, order.retailer_id, lock=True)
        if account is None:
            raise AppException("Retailer has no credit account", ErrorCode.RESOURCE_NOT_FOUND, 404)
        available = available_credit(account)
        if order.grand_total > available and override_reason is None:
            credit_refused = True
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
            raise AppException(
                "Order totals do not match its items", ErrorCode.INTERNAL_SERVER_ERROR, 500
            )

        # 5-6. Deduct stock and record movements (negative = stock leaves the warehouse).
        for product_id, quantity in needed.items():
            inventory[product_id].stock_cases -= quantity
            inventory_repository.add_movement(db, StockMovement(
                product_id=product_id,
                order_id=order.id,
                movement_type=StockMovementType.ORDER_DEDUCTION,
                quantity=-quantity,
                reference=f"Order {order.order_number}",
                created_by=actor.id,
            ))

        # 7. Debit the retailer's credit (V1 policy: the full grand total on approval).
        account.current_outstanding += order.grand_total
        description = f"Order {order.order_number} approved"
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

        # 8-9. Mark approved and commit.
        order.status = OrderStatus.APPROVED
        order.approved_by = actor.id
        order.approved_at = datetime.now(UTC)
        db.commit()
        return order
    except Exception:
        db.rollback()
        if credit_refused:
            _place_on_credit_hold(db, order_id)
        raise


def _place_on_credit_hold(db: Session, order_id: uuid.UUID) -> None:
    """After a refused approval, keep a PENDING order visible as CREDIT_HOLD."""
    order = repository.get_order(db, order_id, lock=True)
    if order is not None and order.status == OrderStatus.PENDING:
        order.status = OrderStatus.CREDIT_HOLD
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
        db.commit()
        return order
    except Exception:
        db.rollback()
        raise


def reject_order(db: Session, actor: User, order_id: uuid.UUID, reason: str) -> Order:
    """Reject with a reason. No stock is deducted and no credit is debited."""
    ensure_role(actor, *ORDER_DESK_ROLES)
    if not reason or not reason.strip():
        raise AppException("A rejection reason is required", ErrorCode.VALIDATION_ERROR, 422)
    try:
        order = repository.get_order(db, order_id, lock=True)
        if order is None:
            raise _not_found("Order", order_id)
        _ensure_open(order)
        order.status = OrderStatus.REJECTED
        order.rejection_reason = reason.strip()
        db.commit()
        return order
    except Exception:
        db.rollback()
        raise
