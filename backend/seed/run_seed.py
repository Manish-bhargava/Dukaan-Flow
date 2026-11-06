"""Seed the database with deterministic demo data, then demo order activity
(seed/demo_activity.py).

Usage (from backend/):  python -m seed.run_seed

Safe to run repeatedly: every row has a fixed UUID and is inserted with
ON CONFLICT DO NOTHING, so existing rows (including any later changes to them) are kept.
"""

import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import (
    Brand,
    Category,
    CreditAccount,
    CreditLedger,
    Inventory,
    Product,
    Retailer,
    RetailerAlias,
    RetailerPrice,
    Scheme,
    StockMovement,
    User,
)
from app.utils.text import normalize_text
from seed import demo_data as d

_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "seed.dukaanflow.local")


def seed_id(*parts: str) -> uuid.UUID:
    """Stable UUID for a seed record, e.g. seed_id("product", "SKU-BS-075")."""
    return uuid.uuid5(_NAMESPACE, ":".join(parts))


def _insert(session: Session, model: type, rows: list[dict[str, Any]]) -> int:
    """Insert rows, skipping any that already exist. Returns the number actually inserted."""
    if not rows:
        return 0
    # A multi-row INSERT takes its column list from the first row, so differing keys would
    # silently drop values. Every row in one batch must provide the same columns.
    if any(row.keys() != rows[0].keys() for row in rows):
        raise ValueError(f"Seed rows for {model.__tablename__} must all have the same keys")
    statement = insert(model).values(rows).on_conflict_do_nothing().returning(model.id)
    return len(session.execute(statement).all())


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def run_seed(session: Session) -> dict[str, tuple[int, int]]:
    """Insert demo data in one transaction. Returns {table: (inserted_now, total_in_table)}."""
    admin_id = seed_id("user", "admin")
    product_ids = {sku: seed_id("product", sku) for sku, *_ in d.PRODUCTS}
    retailer_ids = {key: seed_id("retailer", key) for key in d.RETAILERS}

    plan: list[tuple[type, list[dict[str, Any]]]] = []

    # Staff first: retailers reference their assigned salesman.
    plan.append((User, [
        {"id": seed_id("user", key), "name": name, "phone": phone, "role": role}
        for key, (name, phone, role) in d.STAFF_USERS.items()
    ]))
    plan.append((Retailer, [
        {
            "id": retailer_ids[key],
            "shop_name": r["shop_name"],
            "owner_name": r["owner_name"],
            "phone": r["phone"],
            "address": r["address"],
            "city": d.RETAILER_CITY,
            "gstin": r["gstin"],
            "assigned_salesman_id": seed_id("user", r["salesman"]) if r["salesman"] else None,
        }
        for key, r in d.RETAILERS.items()
    ]))
    plan.append((User, [
        {
            "id": seed_id("user", key),
            "name": name,
            "phone": phone,
            "email": email,
            "role": "RETAILER",
            "retailer_id": retailer_ids[retailer_key],
        }
        for key, (name, phone, email, retailer_key) in d.RETAILER_USERS.items()
    ]))
    plan.append((Category, [{"id": seed_id("category", n), "name": n} for n in d.CATEGORIES]))
    plan.append((Brand, [{"id": seed_id("brand", b), "name": b} for b in sorted({p[2] for p in d.PRODUCTS})]))
    plan.append((Product, [
        {
            "id": product_ids[sku],
            "sku": sku,
            "name": f"{name} {pack}",
            "brand": brand,
            "category_id": seed_id("category", category),
            "pack_size": pack,
            "units_per_case": Decimal(per_case),
            "base_unit": d.BASE_UNIT,
            "order_unit": d.ORDER_UNIT,
            "gst_rate": Decimal(gst),
        }
        for sku, name, brand, category, pack, per_case, _price, _stock, gst in d.PRODUCTS
    ]))

    price_rows = [
        {
            "id": seed_id("price", key, sku, "current"),
            "retailer_id": retailer_ids[key],
            "product_id": product_ids[sku],
            "dealer_price": _money(Decimal(base_price) * r["price_multiplier"]),
            "price_basis": d.DEMO_PRICE_BASIS,
            "tax_inclusive": d.DEMO_TAX_INCLUSIVE,
            "effective_from": d.PRICE_EFFECTIVE_FROM,
            "effective_to": None,
        }
        for key, r in d.RETAILERS.items()
        for sku, _n, _b, _c, _p, _u, base_price, _s, _g in d.PRODUCTS
    ]
    # Default price of every product (the sample dealer price): what retailers without their
    # own price pay, e.g. shops added later by the Admin.
    price_rows += [
        {
            "id": seed_id("price", "default", sku),
            "retailer_id": None,
            "product_id": product_ids[sku],
            "dealer_price": Decimal(base_price),
            "price_basis": d.DEMO_PRICE_BASIS,
            "tax_inclusive": d.DEMO_TAX_INCLUSIVE,
            "effective_from": d.PRICE_EFFECTIVE_FROM,
            "effective_to": None,
        }
        for sku, _n, _b, _c, _p, _u, base_price, _s, _g in d.PRODUCTS
    ]
    price_rows += [
        {
            "id": seed_id("price", key, sku, "historical", start.isoformat()),
            "retailer_id": retailer_ids[key],
            "product_id": product_ids[sku],
            "dealer_price": Decimal(price),
            "price_basis": d.DEMO_PRICE_BASIS,
            "tax_inclusive": d.DEMO_TAX_INCLUSIVE,
            "effective_from": start,
            "effective_to": end,
        }
        for key, sku, price, start, end in d.HISTORICAL_PRICES
    ]
    plan.append((RetailerPrice, price_rows))

    plan.append((Scheme, [
        {
            "id": seed_id("scheme", key),
            "product_id": product_ids[sku],
            "scheme_type": scheme_type,
            "min_quantity": Decimal(min_qty),
            "free_quantity": Decimal(free or 0),
            "discount_percentage": Decimal(pct or 0),
            "starts_at": starts,
            "ends_at": ends,
        }
        for key, sku, scheme_type, min_qty, free, pct, starts, ends in d.SCHEMES
    ]))

    plan.append((Inventory, [
        {"id": seed_id("inventory", sku), "product_id": product_ids[sku], "stock_cases": Decimal(stock)}
        for sku, _n, _b, _c, _p, _u, _price, stock, _g in d.PRODUCTS
    ]))
    # Opening stock is recorded as a movement so inventory is fully traceable.
    plan.append((StockMovement, [
        {
            "id": seed_id("stock_movement", sku, "opening"),
            "product_id": product_ids[sku],
            "movement_type": "RESTOCK",
            "quantity": Decimal(stock),
            "reference": "Opening stock (demo seed)",
            "created_by": admin_id,
            "created_at": d.PRICE_EFFECTIVE_FROM,
        }
        for sku, _n, _b, _c, _p, _u, _price, stock, _g in d.PRODUCTS
        if stock > 0
    ]))

    plan.append((CreditAccount, [
        {
            "id": seed_id("credit_account", key),
            "retailer_id": retailer_ids[key],
            "credit_limit": r["credit_limit"],
            "current_outstanding": r["outstanding"],
        }
        for key, r in d.RETAILERS.items()
    ]))
    # Opening outstanding is recorded in the ledger so the balance is traceable.
    plan.append((CreditLedger, [
        {
            "id": seed_id("credit_ledger", key, "opening"),
            "retailer_id": retailer_ids[key],
            "transaction_type": "ADJUSTMENT",
            "amount": r["outstanding"],
            "description": "Opening outstanding balance (demo seed)",
            "created_by": admin_id,
            "created_at": d.PRICE_EFFECTIVE_FROM,
        }
        for key, r in d.RETAILERS.items()
        if r["outstanding"] != 0
    ]))

    plan.append((RetailerAlias, [
        {
            "id": seed_id("alias", key, normalize_text(alias)),
            "retailer_id": retailer_ids[key],
            "product_id": product_ids[sku],
            "alias": alias,
            "normalized_alias": normalize_text(alias),
        }
        for key, alias, sku in d.ALIASES
    ]))

    inserted: dict[str, int] = {}
    for model, rows in plan:
        table = model.__tablename__
        inserted[table] = inserted.get(table, 0) + _insert(session, model, rows)
    for key, (_name, _phone, email, _retailer) in d.RETAILER_USERS.items():
        session.execute(
            update(User).where(User.id == seed_id("user", key), User.email.is_(None)).values(email=email)
        )
    session.commit()

    return {
        table: (count, session.scalar(select(func.count()).select_from(model)))
        for table, count, model in (
            (model.__tablename__, inserted[model.__tablename__], model)
            for model in dict.fromkeys(m for m, _ in plan)
        )
    }


def set_demo_staff_passwords(session: Session, password: str) -> int:
    """Give internal demo users a password (only those without one). Returns users updated.
    The password comes from DEMO_STAFF_PASSWORD; it is never stored in seed files."""
    from app.core.security import hash_password

    staff_ids = [seed_id("user", key) for key in d.STAFF_USERS]
    result = session.execute(
        update(User)
        .where(User.id.in_(staff_ids), User.password_hash.is_(None))
        .values(password_hash=hash_password(password))
    )
    session.commit()
    return result.rowcount


def main() -> None:
    from app.database.connection import engine
    from app.database.session import SessionLocal
    from seed.demo_activity import run_demo_activity

    with SessionLocal() as session:
        summary = run_seed(session)

    print(f"{'table':<18}{'inserted':>10}{'total':>8}")
    for table, (inserted, total) in summary.items():
        print(f"{table:<18}{inserted:>10}{total:>8}")

    from app.core.config import settings

    if settings.is_development and settings.DEMO_STAFF_PASSWORD:
        with SessionLocal() as session:
            updated = set_demo_staff_passwords(session, settings.DEMO_STAFF_PASSWORD)
        print(f"\ninternal demo users given DEMO_STAFF_PASSWORD: {updated} (existing passwords kept)")
    else:
        print("\nDEMO_STAFF_PASSWORD not set: internal demo users have no password yet")

    # Demo orders/AI activity in ONE transaction: the services' commits become savepoints,
    # so either all of it is created or none of it is.
    with engine.connect() as connection, connection.begin():
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            demo = run_demo_activity(session)
    if demo is None:
        print("\ndemo activity: already present, skipped")
    else:
        print("\ndemo activity created:")
        for number, status in demo.items():
            print(f"  {number}  {status}")


if __name__ == "__main__":
    main()
