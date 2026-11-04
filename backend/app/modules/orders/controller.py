import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.constants import OrderSource, OrderStatus
from app.models import Order, OrderItem, User
from app.modules.orders import service
from app.modules.orders.schemas import (
    AiSourceOut,
    ApproveOrderInput,
    CorrectionOut,
    CorrectOrderItemInput,
    CreateOrderInput,
    OrderItemOut,
    OrderOut,
    OrderPageOut,
    OrderSummaryOut,
    OrderTotalsOut,
    QuoteLineOut,
    QuoteOut,
    RetailerBriefOut,
    RetailerDetailOut,
    SchemeOut,
    StatusReasonInput,
)
from app.utils.responses import success_response


def _scheme_from_snapshot(snapshot: dict | None) -> SchemeOut | None:
    if not snapshot:
        return None
    return SchemeOut(
        scheme_type=snapshot["scheme_type"],
        description=snapshot["description"],
        min_quantity=Decimal(snapshot["min_quantity"]),
        free_quantity=Decimal(snapshot["free_quantity"]),
        discount_percentage=Decimal(snapshot["discount_percentage"]),
    )


def _totals(source) -> OrderTotalsOut:
    return OrderTotalsOut(
        subtotal=source.subtotal, discount_total=source.discount_total,
        taxable_amount=source.taxable_amount, gst_amount=source.gst_amount, grand_total=source.grand_total,
    )


def _item_out(item: OrderItem) -> OrderItemOut:
    return OrderItemOut(
        id=item.id, product_id=item.product_id, product_name=item.product_name, sku=item.sku,
        pack_size=item.product.pack_size, order_unit=item.product.order_unit,
        paid_quantity=item.paid_quantity, free_quantity=item.free_quantity,
        price_basis=item.price_basis, unit_price=item.unit_price, tax_inclusive=item.tax_inclusive,
        discount_percentage=item.discount_percentage, discount_amount=item.discount_amount,
        gst_rate=item.gst_rate, taxable_amount=item.taxable_amount, gst_amount=item.gst_amount,
        line_total=item.line_total, scheme=_scheme_from_snapshot(item.scheme_snapshot),
        corrections=[CorrectionOut.model_validate(c, from_attributes=True)
                     for c in sorted(item.corrections, key=lambda c: c.created_at)],
    )


def order_out(order: Order) -> OrderOut:
    r = order.retailer
    ai = order.ai_extraction
    return OrderOut(
        **_totals(order).model_dump(),
        id=order.id, order_number=order.order_number, status=order.status, source=order.source,
        retailer=RetailerDetailOut(id=r.id, shop_name=r.shop_name, city=r.city, owner_name=r.owner_name,
                                   phone=r.phone, address=r.address, gstin=r.gstin),
        remarks=order.remarks, hold_reason=order.hold_reason, rejection_reason=order.rejection_reason,
        created_at=order.created_at, approved_at=order.approved_at,
        ai=AiSourceOut(extraction_id=ai.id, original_message=ai.original_message) if ai else None,
        items=[_item_out(i) for i in order.items],
    )


def _summary_out(order: Order) -> OrderSummaryOut:
    r = order.retailer
    return OrderSummaryOut(
        id=order.id, order_number=order.order_number, status=order.status, source=order.source,
        retailer=RetailerBriefOut(id=r.id, shop_name=r.shop_name, city=r.city),
        item_count=len(order.items), grand_total=order.grand_total, created_at=order.created_at,
    )


def quote(db: Session, user: User, data: CreateOrderInput) -> dict:
    result = service.quote_order(db, user, data)
    lines = []
    for q in result.lines:
        line, product = q.line, q.product
        lines.append(QuoteLineOut(
            product_id=product.id, sku=product.sku, name=product.name, pack_size=product.pack_size,
            order_unit=product.order_unit, quantity=line.paid_quantity, free_quantity=line.free_quantity,
            price_basis=line.price_basis, unit_price=line.unit_price, tax_inclusive=line.tax_inclusive,
            gst_rate=line.gst_rate, discount_percentage=line.discount_percentage,
            discount_amount=line.discount_amount, taxable_amount=line.taxable_amount,
            gst_amount=line.gst_amount, line_total=line.line_total,
            scheme=_scheme_from_snapshot(line.scheme.snapshot()) if line.scheme else None,
            available_stock=q.available_stock, stock_ok=q.stock_ok,
        ))
    return success_response(
        "Cart priced", QuoteOut(lines=lines, totals=_totals(result.totals), can_order=result.can_order)
    )


def create(db: Session, user: User, data: CreateOrderInput) -> dict:
    order = service.create_order(db, user, data)
    return success_response("Order placed", order_out(order))


def list_orders(
    db: Session, user: User, statuses: list[OrderStatus], source: OrderSource | None,
    search: str | None, page: int, limit: int,
) -> dict:
    orders, total = service.search_orders(
        db, user, statuses=statuses, source=source, search=search, page=page, limit=limit
    )
    return success_response(
        "Orders fetched", OrderPageOut(items=[_summary_out(o) for o in orders], page=page, limit=limit, total=total)
    )


def get(db: Session, user: User, order_id: uuid.UUID) -> dict:
    return success_response("Order fetched", order_out(service.get_order(db, user, order_id)))


def correct_item(db: Session, user: User, order_id: uuid.UUID, item_id: uuid.UUID, data: CorrectOrderItemInput) -> dict:
    service.correct_order_item(db, user, order_id, item_id, data)
    return success_response("Order item corrected", order_out(service.get_order(db, user, order_id)))


def hold(db: Session, user: User, order_id: uuid.UUID, data: StatusReasonInput) -> dict:
    return success_response("Order put on hold", order_out(service.hold_order(db, user, order_id, data.reason)))


def approve(db: Session, user: User, order_id: uuid.UUID, data: ApproveOrderInput) -> dict:
    order = service.approve_order(db, user, order_id, data.credit_override_reason)
    return success_response("Order confirmed", order_out(order))


def reject(db: Session, user: User, order_id: uuid.UUID, data: StatusReasonInput) -> dict:
    return success_response("Order rejected", order_out(service.reject_order(db, user, order_id, data.reason)))


def summary(db: Session, user: User) -> dict:
    return success_response("Order counts", service.status_counts(db, user))
