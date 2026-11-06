"""Salesman field work: the offline sync bundle and shop visits.

Everything is limited to the retailers assigned to the signed-in salesman (and active).
Orders are placed through the normal order service (POST /orders with retailer_id), so
pricing, schemes, stock and credit rules are exactly those of every other order.
"""

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.constants import ErrorCode, PriceBasis, UserRole
from app.core.permissions import ensure_role, forbidden
from app.exceptions.base import AppException
from app.models import Retailer, SalesmanSyncStatus, ShopVisit, User
from app.modules.orders import repository as orders_repository
from app.modules.pricing import repository as pricing_repository
from app.modules.pricing.service import money
from app.modules.products import images
from app.modules.products import repository as products_repository
from app.modules.products.schemas import CategoryOut, PriceOut, SchemeOut
from app.modules.retailers import repository as retailers_repository
from app.modules.retailers.schemas import CreditOut
from app.modules.retailers.service import credit_summary, get_retailer_for
from app.modules.salesman import repository
from app.modules.salesman.schemas import (
    SyncStatusInput,
    AssignedRetailerOut,
    BundleProductOut,
    RecentOrderOut,
    SalesmanHomeOut,
    SyncBundleOut,
    TodayVisitOut,
    VisitInput,
)
from app.modules.schemes import engine as schemes_engine

IST = ZoneInfo("Asia/Kolkata")


def sync_bundle(db: Session, actor: User) -> SyncBundleOut:
    ensure_role(actor, UserRole.SALESMAN)
    now = datetime.now(UTC)
    retailers = repository.assigned_active_retailers(db, actor.id)

    retailer_outs = []
    login_phones = repository.retailer_login_phones(db, [r.id for r in retailers])
    prices: dict[str, dict[str, PriceOut]] = {}
    product_ids: set[uuid.UUID] = set()
    for retailer in retailers:
        account = retailers_repository.get_credit_account(db, retailer.id)
        summary = credit_summary(db, account) if account else None
        recent = repository.recent_orders(db, retailer.id)
        retailer_outs.append(AssignedRetailerOut(
            id=retailer.id, shop_name=retailer.shop_name, owner_name=retailer.owner_name, phone=retailer.phone,
            address=retailer.address, city=retailer.city, gstin=retailer.gstin,
            registered_mobiles=login_phones.get(retailer.id, []),
            last_order_at=recent[0].created_at if recent else None,
            ordering_restricted_reason=retailer.ordering_restricted_reason,
            credit=CreditOut(
                credit_limit=summary.credit_limit, current_outstanding=summary.current_outstanding,
                reserved_for_review=summary.reserved_for_review, available_credit=summary.available_credit,
            ) if summary else None,
            recent_orders=[RecentOrderOut(id=o.id, order_number=o.order_number, created_at=o.created_at,
                                          grand_total=o.grand_total, status=o.status, item_count=len(o.items))
                           for o in recent],
        ))
        effective = pricing_repository.get_effective_prices(db, retailer.id, now)
        prices[str(retailer.id)] = {}
        for product_id, price in effective.items():
            prices[str(retailer.id)][str(product_id)] = price  # converted below once products are known
        product_ids.update(effective.keys())

    products, _ = products_repository.list_products(db, product_ids, None, None, 0, max(len(product_ids), 1))
    by_id = {p.id: p for p in products}
    stock = products_repository.get_stock(db, list(by_id))
    schemes = pricing_repository.get_active_schemes(db, now, list(by_id))

    for retailer_id, per_product in prices.items():
        prices[retailer_id] = {
            pid: PriceOut(
                dealer_price=price.dealer_price, price_basis=price.price_basis, tax_inclusive=price.tax_inclusive,
                case_price=money(price.dealer_price * by_id[uuid.UUID(pid)].units_per_case
                                 if price.price_basis == PriceBasis.PIECE else price.dealer_price),
            )
            for pid, price in per_product.items()
            if uuid.UUID(pid) in by_id  # inactive products are not sold
        }

    _sync_status(db, actor).last_sync_at = now
    db.commit()
    return SyncBundleOut(
        synced_at=now,
        retailers=retailer_outs,
        categories=sorted({p.category.id: CategoryOut(id=p.category.id, name=p.category.name) for p in products}.values(),
                          key=lambda c: c.name),
        products=[
            BundleProductOut(
                id=p.id, sku=p.sku, name=p.name, brand=p.brand, category=CategoryOut(id=p.category.id, name=p.category.name),
                pack_size=p.pack_size, units_per_case=p.units_per_case, base_unit=p.base_unit, order_unit=p.order_unit,
                gst_rate=p.gst_rate,
                image_url=images.delivery_url(p.image_url, images.LARGE),
                thumbnail_url=images.delivery_url(p.image_url, images.THUMBNAIL),
                stock_cases=stock.get(p.id, Decimal("0")), in_stock=stock.get(p.id, Decimal("0")) > 0,
                schemes=[SchemeOut(id=s.id, description=schemes_engine.describe(s), scheme_type=s.scheme_type,
                                   min_quantity=s.min_quantity, free_quantity=s.free_quantity,
                                   discount_percentage=s.discount_percentage)
                         for s in schemes.get(p.id, [])],
            )
            for p in products
        ],
        prices=prices,
    )


def _sync_status(db: Session, actor: User) -> SalesmanSyncStatus:
    status = db.get(SalesmanSyncStatus, actor.id)
    if status is None:
        status = SalesmanSyncStatus(user_id=actor.id, pending_orders=0, failed_orders=0, pending_visits=0)
        db.add(status)
    return status


def report_sync_status(db: Session, actor: User, data: SyncStatusInput) -> SalesmanSyncStatus:
    """The phone reports its outbox after each sync run (the outbox itself stays on the phone)."""
    ensure_role(actor, UserRole.SALESMAN)
    status = _sync_status(db, actor)
    status.pending_orders, status.failed_orders, status.pending_visits = (
        data.pending_orders, data.failed_orders, data.pending_visits)
    status.last_error = data.last_error
    status.reported_at = datetime.now(UTC)
    db.commit()
    return status


def home(db: Session, actor: User) -> SalesmanHomeOut:
    """Counts for the salesman's home screen, from the database (today = IST calendar day)."""
    ensure_role(actor, UserRole.SALESMAN)
    start = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    retailers = {r.id: r for r in repository.assigned_active_retailers(db, actor.id)}
    visits = repository.visits_between(db, actor.id, start, end)
    names = {r.id: r.shop_name for r in retailers.values()}
    for visit in visits:  # a visit may belong to a shop that is no longer assigned/active
        if visit.retailer_id not in names:
            other = db.get(Retailer, visit.retailer_id)
            names[visit.retailer_id] = other.shop_name if other else "Unknown shop"
    return SalesmanHomeOut(
        date=start.date().isoformat(),
        assigned_retailers=len(retailers),
        visits_today=len(visits),
        orders_today=repository.orders_created_between(db, actor.id, start, end),
        todays_visits=[TodayVisitOut(id=v.id, retailer_id=v.retailer_id, shop_name=names[v.retailer_id],
                                     started_at=v.started_at, ended_at=v.ended_at, outcome=v.outcome) for v in visits],
    )


def record_visit(db: Session, actor: User, data: VisitInput) -> ShopVisit:
    """Create or update a visit (same id = same visit, so offline retries are safe)."""
    ensure_role(actor, UserRole.SALESMAN)
    retailer = get_retailer_for(db, actor, data.retailer_id)  # 403 unless assigned to this salesman
    if data.ended_at is not None and data.ended_at < data.started_at:
        raise AppException("A visit cannot end before it starts", ErrorCode.VALIDATION_ERROR, 422)
    order_id = None
    if data.client_order_id:
        order = orders_repository.get_order_by_client_id(db, data.client_order_id)
        if order is not None and order.created_by == actor.id and order.retailer_id == retailer.id:
            order_id = order.id
    try:
        visit = repository.get_visit(db, data.id)
        if visit is None:
            visit = ShopVisit(id=data.id, salesman_id=actor.id, retailer_id=retailer.id, started_at=data.started_at)
            db.add(visit)
        elif visit.salesman_id != actor.id or visit.retailer_id != retailer.id:
            raise forbidden("This visit belongs to someone else")
        visit.ended_at = data.ended_at
        visit.outcome = data.outcome
        # Linked once the order has synced; the app sends the visit again after syncing orders.
        visit.order_id = order_id or visit.order_id
        db.commit()
        return visit
    except Exception:
        db.rollback()
        raise
