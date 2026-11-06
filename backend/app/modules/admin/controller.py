"""Admin HTTP layer: calls the admin services and shapes their results (money and quantities
as decimal strings, like the rest of the API)."""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.models import AuditLog, Order, Product, Retailer, RetailerPrice, Scheme, User
from app.modules.admin import catalog, monitoring, people, reports
from app.modules.audit.service import _plain
from app.modules.order_desk.service import salesman_of
from app.modules.products import images
from app.modules.schemes import engine as schemes_engine
from app.utils.responses import success_response


def ok(message: str, data) -> dict:
    return success_response(message, _plain(data))


def page(items, total, page_no, limit) -> dict:
    return {"items": items, "total": total, "page": page_no, "limit": limit}


# ---------------------------------------------------------------- shapes


def person(u: User | None) -> dict | None:
    return {"id": u.id, "name": u.name, "phone": u.phone, "role": u.role, "is_active": u.is_active} if u else None


def user_out(u: User) -> dict:
    return {"id": u.id, "name": u.name, "phone": u.phone, "email": u.email, "role": u.role, "is_active": u.is_active,
            "last_login_at": u.last_login_at, "created_at": u.created_at, "has_password": u.password_hash is not None,
            "retailer": {"id": u.retailer.id, "shop_name": u.retailer.shop_name} if u.retailer else None}


def retailer_out(r: Retailer) -> dict:
    return {"id": r.id, "shop_name": r.shop_name, "owner_name": r.owner_name, "phone": r.phone, "address": r.address,
            "city": r.city, "gstin": r.gstin, "is_active": r.is_active, "created_at": r.created_at,
            "ordering_restricted_reason": r.ordering_restricted_reason, "salesman": person(r.assigned_salesman)}


def order_brief(o: Order) -> dict:
    s = salesman_of(o) if o.creator else None
    return {"id": o.id, "order_number": o.order_number, "status": o.status, "source": o.source,
            "grand_total": o.grand_total, "created_at": o.created_at, "item_count": len(o.items),
            "retailer": {"id": o.retailer.id, "shop_name": o.retailer.shop_name}, "salesman": s.name if s else None,
            "created_offline": o.created_offline}


def price_out(p: RetailerPrice | None) -> dict | None:
    if p is None:
        return None
    return {"dealer_price": p.dealer_price, "price_basis": p.price_basis, "tax_inclusive": p.tax_inclusive,
            "effective_from": p.effective_from, "effective_to": p.effective_to}


def product_out(p: Product, stock=None) -> dict:
    return {"id": p.id, "sku": p.sku, "name": p.name, "brand": p.brand,
            "category": {"id": p.category.id, "name": p.category.name, "is_active": p.category.is_active},
            "pack_size": p.pack_size, "units_per_case": p.units_per_case, "base_unit": p.base_unit,
            "order_unit": p.order_unit, "gst_rate": p.gst_rate, "is_active": p.is_active,
            "thumbnail_url": images.delivery_url(p.image_url, images.THUMBNAIL),
            "image_url": images.delivery_url(p.image_url, images.LARGE),
            "created_at": p.created_at, "updated_at": p.updated_at, "stock": stock}


def scheme_out(s: Scheme, now: datetime) -> dict:
    return {"id": s.id, "product": {"id": s.product.id, "sku": s.product.sku, "name": s.product.name},
            "scheme_type": s.scheme_type, "description": schemes_engine.describe(s), "min_quantity": s.min_quantity,
            "free_quantity": s.free_quantity, "discount_percentage": s.discount_percentage, "starts_at": s.starts_at,
            "ends_at": s.ends_at, "is_active": s.is_active, "state": catalog.scheme_state(s, now)}


def audit_out(row) -> dict:
    return {"id": row["id"], "at": row["at"], "action": row["action"], "entity_type": row["entity_type"],
            "entity_id": row["entity_id"], "label": row["label"], "details": row["details"], "message": row["message"],
            "actor": {"id": row["actor_id"], "name": row["actor_name"], "role": row["actor_role"]} if row["actor_id"] else None}


def sync_out(s) -> dict | None:
    if s is None:
        return None
    return {"last_sync_at": s.last_sync_at, "reported_at": s.reported_at, "pending_orders": s.pending_orders,
            "failed_orders": s.failed_orders, "pending_visits": s.pending_visits, "last_error": s.last_error}


def failure_out(f: AuditLog) -> dict:
    d = f.details or {}
    return {"id": f.id, "at": f.created_at, "client_order_id": f.entity_label, "salesman": f.actor.name if f.actor else None,
            "error_code": d.get("error_code"), "message": d.get("message"), "retailer_id": d.get("retailer_id"),
            "created_offline": d.get("created_offline"), "items": d.get("items")}


# ---------------------------------------------------------------- dashboard and monitoring


def dashboard(db: Session, user: User) -> dict:
    d = monitoring.dashboard(db, user)
    d["low_stock"] = [{"product": product_out(p), "stock": s} for p, s in d["low_stock"]]
    d["inactive"] = [{"retailer": retailer_out(r), "last_order_at": last} for r, last in d["inactive"]]
    d["recent_orders"] = [order_brief(o) for o in d["recent_orders"]]
    d["recent_retailers"] = [retailer_out(r) for r in d["recent_retailers"]]
    d["recent_products"] = [product_out(p) for p in d["recent_products"]]
    d["recent_visits"] = [{"salesman": name, "shop_name": shop, "started_at": v.started_at, "ended_at": v.ended_at,
                           "outcome": v.outcome, "order_number": number, "order_total": total, "order_id": v.order_id}
                          for v, name, shop, number, total in d["recent_visits"]]
    return ok("Admin dashboard", d)


def order_desk(db: Session, user: User) -> dict:
    d = monitoring.order_desk_oversight(db, user)
    d["recent"] = [audit_out(r) for r in d["recent"]]
    return ok("Order desk activity", d)


def audit(db: Session, user: User, **kw) -> dict:
    rows, total = monitoring.audit(db, user, **kw)
    return ok("Audit log", page([audit_out(r) for r in rows], total, kw["page"], kw["limit"]))


def ai_orders(db: Session, user: User, state, page_no, limit) -> dict:
    d = monitoring.ai_orders(db, user, state=state, page=page_no, limit=limit)
    items = []
    for ex, order in d["rows"]:
        items.append({
            "id": ex.id, "created_at": ex.created_at, "original_message": ex.original_message,
            "status": ex.extraction_status, "model_name": ex.model_name, "retailer_id": ex.retailer_id,
            "input_type": ex.input_type,
            "lines": [{"original_text": i.original_text, "extracted_name": i.extracted_name, "quantity": i.quantity,
                       "unit": i.unit, "matched_product_id": i.matched_product_id, "confidence": i.confidence,
                       "alternatives": i.alternatives or [], "requires_clarification": i.requires_clarification,
                       "evidence": i.evidence or [], "clarification_reason": i.clarification_reason}
                      for i in ex.items],
            "order": {"id": order.id, "order_number": order.order_number, "status": order.status,
                      "grand_total": order.grand_total} if order else None,
        })
    shops = {r.id: r.shop_name for r in db.query(Retailer).filter(Retailer.id.in_({i["retailer_id"] for i in items}))}
    for i in items:
        i["shop_name"] = shops.get(i["retailer_id"])
    return ok("AI orders", {**page(items, d["total"], page_no, limit), "stats": d["stats"],
                            "low_confidence_percent": d["low_confidence"]})


def sync(db: Session, user: User) -> dict:
    d = monitoring.sync_monitor(db, user)
    return ok("Offline sync", {
        "salesmen": [{"salesman": person(s["user"]), "sync": sync_out(s["sync"])} for s in d["salesmen"]],
        "offline_counts": d["offline_counts"],
        "offline_orders": [{**order_brief_light(o), "hold_reason": o.hold_reason, "rejection_reason": o.rejection_reason,
                            "client_created_at": o.client_created_at, "client_order_id": o.client_order_id,
                            "salesman": o.creator.name} for o in d["offline_orders"]],
        "failures": [failure_out(f) for f in d["failures"]],
        "failures_7d": d["failures_7d"],
    })


def order_brief_light(o: Order) -> dict:
    return {"id": o.id, "order_number": o.order_number, "status": o.status, "grand_total": o.grand_total,
            "created_at": o.created_at, "retailer": {"id": o.retailer.id, "shop_name": o.retailer.shop_name}}


def settings(db: Session, user: User) -> dict:
    return ok("Settings", monitoring.read_settings(db, user).model_dump())


def update_settings(db: Session, user: User, data) -> dict:
    return ok("Settings saved", monitoring.update_settings(db, user, data).model_dump())


# ---------------------------------------------------------------- retailers and credit


def list_retailers(db: Session, user: User, *, search, status, salesman_id, sort, page_no, limit) -> dict:
    rows, total = people.list_retailers(db, user, search=search, status=status, salesman_id=salesman_id, sort=sort,
                                        page=page_no, limit=limit)
    items = []
    for r, account, last, bought in rows:
        items.append({**retailer_out(r), "credit_limit": account.credit_limit if account else None,
                      "outstanding": account.current_outstanding if account else None,
                      "last_order_at": last, "total_purchased": bought or 0})
    return ok("Retailers", page(items, total, page_no, limit))


def retailer_detail(db: Session, retailer_id: uuid.UUID, user: User) -> dict:
    d = people.get_retailer(db, user, retailer_id)
    credit = d["credit"]
    stats = d["stats"]
    purchased = stats.get("APPROVED", (0, 0))
    return ok("Retailer", {
        **retailer_out(d["retailer"]),
        "credit": {"credit_limit": credit.credit_limit, "current_outstanding": credit.current_outstanding,
                   "reserved_for_review": credit.reserved_for_review, "available_credit": credit.available_credit}
        if credit else None,
        "purchases": {"total_orders": sum(c for c, _ in stats.values()), "confirmed_orders": purchased[0],
                      "total_purchased": purchased[1],
                      "open_orders": sum(stats.get(s, (0, 0))[0] for s in people.open_statuses()),
                      "rejected_orders": stats.get("REJECTED", (0, 0))[0]},
        "logins": [{"id": u.id, "phone": u.phone, "email": u.email, "is_active": u.is_active,
                    "last_login_at": u.last_login_at} for u in d["users"]],
        "recent_orders": [order_brief(o) for o in d["recent_orders"]],
    })


def create_retailer(db, user, data) -> dict:
    return ok("Retailer created", {"id": people.create_retailer(db, user, data).id})


def update_retailer(db, user, retailer_id, data) -> dict:
    people.update_retailer(db, user, retailer_id, data)
    return retailer_detail(db, retailer_id, user)


def update_credit(db, user, retailer_id, data) -> dict:
    people.update_credit(db, user, retailer_id, data)
    return retailer_detail(db, retailer_id, user)


def credit_history(db, user, retailer_id) -> dict:
    d = people.credit_history(db, user, retailer_id)
    return ok("Credit history", {
        "ledger": [{"id": e.id, "type": e.transaction_type, "amount": e.amount, "description": e.description,
                    "order_number": number, "by": by, "at": e.created_at} for e, number, by in d["ledger"]],
        "changes": [audit_out(r) for r in d["changes"]],
    })


def retailer_prices(db, user, retailer_id) -> dict:
    rows = catalog.retailer_prices(db, user, retailer_id)
    return ok("Retailer prices", [{
        "product": {"id": r["product"].id, "sku": r["product"].sku, "name": r["product"].name,
                    "brand": r["product"].brand, "order_unit": r["product"].order_unit},
        "default": price_out(r["default"]), "own": price_out(r["own"]),
        "effective": price_out(r["own"] or r["default"]), "schemes": r["schemes"]} for r in rows])


# ---------------------------------------------------------------- salesmen, assignments, users


def list_salesmen(db, user) -> dict:
    out = []
    for s in people.list_salesmen(db, user):
        orders, value, offline = s["orders_30d"]
        visits, converted, _ = s["visits_30d"]
        out.append({**user_out(s["user"]), "assigned_retailers": s["assigned"], "orders_30d": orders,
                    "confirmed_value_30d": value, "offline_orders_30d": offline, "visits_30d": visits,
                    "visits_with_order_30d": converted, "last_visit_at": s["last_visit_at"], "sync": sync_out(s["sync"])})
    return ok("Salesmen", out)


def salesman_detail(db, user, salesman_id) -> dict:
    d = people.get_salesman(db, user, salesman_id)
    orders, value, offline = d["orders_30d"]
    visits, converted, last = d["visits_30d"]
    return ok("Salesman", {
        **user_out(d["user"]),
        "stats_30d": {"orders": orders, "confirmed_value": value, "offline_orders": offline, "visits": visits,
                      "visits_with_order": converted},
        "activity": d["activity"],
        "sync": sync_out(d["sync"]),
        "retailers": [{**retailer_out(r), "outstanding": r.credit_account.current_outstanding if r.credit_account else None,
                       "credit_limit": r.credit_account.credit_limit if r.credit_account else None} for r in d["retailers"]],
        "visits": [{"id": v.id, "shop_name": shop, "started_at": v.started_at, "ended_at": v.ended_at,
                    "outcome": v.outcome, "order_id": v.order_id, "order_number": number, "order_status": status}
                   for v, shop, number, status in d["visits"]],
        "sync_failures": [failure_out(f) for f in d["failures"]],
    })


def assign(db, user, data) -> dict:
    moved = people.assign(db, user, data)
    return ok(f"{len(moved)} retailer(s) updated", {"changed": [r.id for r in moved]})


def list_users(db, user, *, role, search, status, page_no, limit) -> dict:
    users, total = people.list_users(db, user, role=role, search=search, status=status, page=page_no, limit=limit)
    return ok("Users", page([user_out(u) for u in users], total, page_no, limit))


def user_detail(db, user, user_id) -> dict:
    d = people.get_user(db, user, user_id)
    return ok("User", {**user_out(d["user"]), "activity": d["activity"], "recent": [audit_out(r) for r in d["recent"]]})


def create_user(db, user, data) -> dict:
    return ok("User created", user_out(people.create_user(db, user, data)))


def update_user(db, user, user_id, data) -> dict:
    return ok("User updated", user_out(people.update_user(db, user, user_id, data)))


def reset_password(db, user, user_id, data) -> dict:
    people.reset_password(db, user, user_id, data)
    return ok("Password reset", {})


# ---------------------------------------------------------------- catalogue


def categories(db, user) -> dict:
    return ok("Categories", [{"id": c.id, "name": c.name, "is_active": c.is_active, "products": n}
                             for c, n in catalog.list_categories(db, user)])


def create_category(db, user, data) -> dict:
    c = catalog.create_category(db, user, data)
    return ok("Category created", {"id": c.id, "name": c.name, "is_active": c.is_active})


def update_category(db, user, category_id, data) -> dict:
    c = catalog.update_category(db, user, category_id, data)
    return ok("Category updated", {"id": c.id, "name": c.name, "is_active": c.is_active})


def create_brand(db, user, data) -> dict:
    b = catalog.create_brand(db, user, data)
    return ok("Brand created", {"id": b.id, "name": b.name, "is_active": b.is_active})


def update_brand(db, user, brand_id, data) -> dict:
    b = catalog.update_brand(db, user, brand_id, data)
    return ok("Brand updated", {"id": b.id, "name": b.name, "is_active": b.is_active})


def brands(db, user) -> dict:
    return ok("Brands", [{"id": b.id, "name": b.name, "is_active": b.is_active, "products": n}
                         for b, n in catalog.list_brands(db, user)])


def list_products(db, user, *, page_no, limit, **kw) -> dict:
    d = catalog.list_products(db, user, page=page_no, limit=limit, **kw)
    items = [{**product_out(p, inv.stock_cases if inv else 0), "default_price": price_out(d["defaults"].get(p.id)),
              "retailer_prices": d["overrides"].get(p.id, 0)} for p, inv in d["rows"]]
    return ok("Products", {**page(items, d["total"], page_no, limit), "low_stock": d["low_stock"]})


def product_detail(db, user, product_id) -> dict:
    d = catalog.get_product(db, user, product_id)
    now = datetime.now(UTC)
    return ok("Product", {
        **product_out(d["product"], d["stock"]), "stock_updated_at": d["stock_updated_at"], "low_stock": d["low_stock"],
        "default_price": price_out(d["default_price"]),
        "price_history": [{**price_out(p), "id": p.id, "retailer": {"id": p.retailer_id, "shop_name": shop} if p.retailer_id else None,
                           "by": by, "created_at": p.created_at} for p, shop, by in d["price_history"]],
        "schemes": [scheme_out(s, now) for s in d["schemes"]],
        "movements": [movement_out(m, after, by, number) for m, after, by, number in d["movements"]],
    })


def movement_out(m, after, by, number) -> dict:
    return {"id": m.id, "type": m.movement_type, "change": m.quantity, "stock_after": after,
            "stock_before": (after - m.quantity) if after is not None else None, "reason": m.reference,
            "order_id": m.order_id, "order_number": number, "by": by, "at": m.created_at}


def create_product(db, user, data) -> dict:
    return ok("Product created", {"id": catalog.create_product(db, user, data).id})


def update_product(db, user, product_id, data) -> dict:
    catalog.update_product(db, user, product_id, data)
    return product_detail(db, user, product_id)


def set_price(db, user, data) -> dict:
    return ok("Price saved", price_out(catalog.set_price(db, user, data)))


def remove_price(db, user, product_id, retailer_id) -> dict:
    catalog.remove_retailer_price(db, user, product_id, retailer_id)
    return ok("Retailer price removed; the default price applies", {})


def list_schemes(db, user, *, page_no, limit, **kw) -> dict:
    items, total = catalog.list_schemes(db, user, page=page_no, limit=limit, **kw)
    now = datetime.now(UTC)
    return ok("Schemes", page([scheme_out(s, now) for s in items], total, page_no, limit))


def create_schemes(db, user, data) -> dict:
    now = datetime.now(UTC)
    return ok("Scheme created", [scheme_out(s, now) for s in catalog.create_schemes(db, user, data)])


def update_scheme(db, user, scheme_id, data) -> dict:
    return ok("Scheme updated", scheme_out(catalog.update_scheme(db, user, scheme_id, data), datetime.now(UTC)))


def list_stock(db, user, *, page_no, limit, **kw) -> dict:
    d = catalog.list_stock(db, user, page=page_no, limit=limit, **kw)
    items = [{**product_out(p, inv.stock_cases if inv else 0), "stock_updated_at": inv.updated_at if inv else None,
              "last_movement_at": d["last_movement"].get(p.id)} for p, inv in d["rows"]]
    return ok("Stock", {**page(items, d["total"], page_no, limit), "low_stock": d["low_stock"]})


def adjust_stock(db, user, product_id, data) -> dict:
    m = catalog.adjust_stock(db, user, product_id, data)
    return ok("Stock updated", {"change": m.quantity, "stock_after": m.stock_after,
                                "stock_before": m.stock_after - m.quantity})


def stock_history(db, user, product_id) -> dict:
    return ok("Stock history", [movement_out(*row) for row in catalog.stock_history(db, user, product_id)])


# ---------------------------------------------------------------- reports


def report(db, user, name: str, from_date: date | None, to_date: date | None) -> dict:
    return ok("Report", reports.run(db, user, name, from_date, to_date))


def report_csv(db, user, name: str, from_date: date | None, to_date: date | None) -> tuple[str, str]:
    data = reports.run(db, user, name, from_date, to_date)
    suffix = f"-{from_date or 'start'}-to-{to_date or 'today'}" if data["uses_dates"] else ""
    return reports.to_csv(_plain(data)), f"dukaanflow-{name}{suffix}.csv"


def report_list() -> dict:
    return ok("Reports", reports.catalogue())
