import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.core.constants import OrderSource, OrderStatus
from app.models import Order, OrderEvent, User
from app.modules.order_desk import service
from app.modules.order_desk.schemas import (
    AiLineOut,
    AiProductOut,
    BeatOut,
    DeskOrderPageOut,
    DeskOrderRowOut,
    DeskRetailerOut,
    DispatchOut,
    EventOut,
    LineStockOut,
    OrderReviewOut,
    OverviewOut,
    PersonOut,
    ProductTotalOut,
    StopOrderOut,
    StopOut,
    WarningOut,
)
from app.modules.orders.controller import order_out
from app.modules.orders.repository import get_products
from app.modules.orders.schemas import CreatorOut
from app.modules.retailers.schemas import CreditOut
from app.utils.responses import success_response


def _person(user: User | None) -> PersonOut | None:
    return PersonOut(id=user.id, name=user.name, phone=user.phone) if user else None


def _creator(user: User | None) -> CreatorOut | None:
    return CreatorOut(id=user.id, name=user.name, role=user.role) if user else None


def _event(e: OrderEvent | None) -> EventOut | None:
    if e is None:
        return None
    return EventOut(action=e.action, actor=_creator(e.actor), message=e.message, details=e.details, created_at=e.created_at)


def _warnings(items) -> list[WarningOut]:
    return [WarningOut(code=w.code, severity=w.severity, message=w.message) for w in items]


def _reason(order: Order) -> str | None:
    if order.status == OrderStatus.REJECTED:
        return order.rejection_reason
    if order.status == OrderStatus.CLARIFICATION_REQUIRED:
        return order.clarification_message
    if order.status == OrderStatus.ON_HOLD:
        return order.hold_reason
    return None


def _row(row: service.DeskRow) -> DeskOrderRowOut:
    o, r = row.order, row.order.retailer
    return DeskOrderRowOut(
        id=o.id, order_number=o.order_number, status=o.status, source=o.source,
        retailer=DeskRetailerOut(id=r.id, shop_name=r.shop_name, owner_name=r.owner_name, phone=r.phone, city=r.city),
        salesman=_person(row.salesman), created_by=_creator(o.creator), item_count=len(o.items),
        grand_total=o.grand_total, created_at=o.created_at, approved_at=o.approved_at,
        approved_by=_creator(o.approver), created_offline=o.created_offline,
        tally_exported_at=o.tally_exported_at, reason=_reason(o),
        warnings=_warnings(row.warnings), last_action=_event(row.last_event),
    )


def list_orders(db: Session, user: User, *, view: str, statuses: list[OrderStatus], source: OrderSource | None,
                search: str | None, salesman_id: uuid.UUID | None, from_date: date | None, to_date: date | None,
                exported: bool | None, sort: str, page: int, limit: int, retailer_id: uuid.UUID | None = None) -> dict:
    rows, total = service.list_orders(
        db, user, view=view, statuses=statuses, source=source, search=search, salesman_id=salesman_id,
        from_date=from_date, to_date=to_date, exported=exported, sort=sort, page=page, limit=limit,
        retailer_id=retailer_id,
    )
    return success_response("Orders fetched",
                            DeskOrderPageOut(items=[_row(r) for r in rows], page=page, limit=limit, total=total))


def review(db: Session, user: User, order_id: uuid.UUID) -> dict:
    data = service.review(db, user, order_id)
    o = data.order
    ai_items = o.ai_extraction.items if o.ai_extraction else []
    products = get_products(db, [i.matched_product_id for i in ai_items if i.matched_product_id])
    ai_lines = []
    for i in ai_items:
        p = products.get(i.matched_product_id)
        ai_lines.append(AiLineOut(
            original_text=i.original_text, extracted_name=i.extracted_name, quantity=i.quantity, unit=i.unit,
            product=AiProductOut(id=p.id, sku=p.sku, name=p.name, pack_size=p.pack_size) if p else None,
            confidence=i.confidence, requires_clarification=i.requires_clarification,
            clarification_reason=i.clarification_reason, evidence=i.evidence or [], alternatives=i.alternatives or [],
        ))
    return success_response("Order review", OrderReviewOut(
        order=order_out(o),
        salesman=_person(data.salesman),
        credit=CreditOut.model_validate(data.credit, from_attributes=True) if data.credit else None,
        stock=[LineStockOut(item_id=s.item_id, needed=s.needed, available=s.available, ok=s.ok) for s in data.stock],
        warnings=_warnings(data.warnings),
        ai_input_type=o.ai_extraction.input_type if o.ai_extraction else None,
        ai_lines=ai_lines,
        history=[_event(e) for e in data.events],
    ))


def overview(db: Session, user: User) -> dict:
    return success_response("Order desk overview", OverviewOut(**service.overview(db, user)))


def summary(db: Session, user: User) -> dict:
    return success_response("Order counts", service.status_counts(db, user))


def salesmen(db: Session, user: User) -> dict:
    return success_response("Salesmen", [_person(u) for u in service.salesmen(db, user)])


def _products(rows) -> list[ProductTotalOut]:
    return [ProductTotalOut(product_id=r.product_id, sku=r.sku, name=r.name, pack_size=r.pack_size,
                            order_unit=r.order_unit, paid=r.paid, free=r.free, total=r.total, orders=r.orders)
            for r in rows]


def _stop(stop: service.Stop) -> StopOut:
    r = stop.retailer
    return StopOut(
        retailer_id=r.id, shop_name=r.shop_name, owner_name=r.owner_name, phone=r.phone, address=r.address,
        city=r.city, grand_total=sum((o.grand_total for o in stop.orders), start=0),
        orders=[StopOrderOut(order_id=o.id, order_number=o.order_number, grand_total=o.grand_total,
                             approved_at=o.approved_at) for o in stop.orders],
        products=_products(stop.products),
    )


def dispatch(db: Session, user: User, from_date: date | None, to_date: date | None, salesman_id: uuid.UUID | None) -> dict:
    data = service.dispatch(db, user, from_date, to_date, salesman_id)
    return success_response("Dispatch preparation", DispatchOut(
        order_count=len(data.orders),
        grand_total=sum((o.grand_total for o in data.orders), start=0),
        products=_products(data.products),
        beats=[BeatOut(salesman=_person(b.salesman), stops=[_stop(s) for s in b.stops], products=_products(b.products),
                       orders_count=len(b.orders), grand_total=sum((o.grand_total for o in b.orders), start=0)) for b in data.beats],
    ))
