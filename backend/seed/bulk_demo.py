"""Extra demo data for a fuller local database (development only; never used by tests).

Adds, on top of `seed.run_seed`:
  - 2 more salesmen (4 in total), each with 10 assigned retailers, and 2 more order desk
    users (3 in total); every retailer has a login account, credit account and its own
    prices for every product;
  - 4 more categories and products up to 100 in total, with stock, a few schemes and aliases;
  - about 30 days of activity, created through the real services so pricing, schemes,
    stock, credit and order statuses follow the same rules as the app:
      * retailer catalogue and salesman orders, accepted or rejected by the Order Desk,
      * salesman shop visits, with an order or without one,
      * AI-captured orders that the Order Desk confirms, rejects or has not reviewed yet,
      * retailer payments (credit ledger) and restocks (stock movements).

All people, shops, numbers, GSTINs and brands are fictional. Running it again does nothing
(if the first bulk order exists, the activity is skipped; master rows use fixed ids).

    .venv/bin/python -m seed.bulk_demo --staff-password 'choose-a-password'
"""

import argparse
import random
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.exceptions.base import AppException
from app.models import (
    AiExtraction,
    Brand,
    Category,
    CreditAccount,
    CreditLedger,
    Inventory,
    Order,
    OrderEvent,
    Product,
    Retailer,
    RetailerAlias,
    RetailerPrice,
    Scheme,
    ShopVisit,
    StockMovement,
    User,
)
from app.modules.ai_orders import service as ai_orders
from app.modules.ai_orders.schemas import (
    ConfirmedItemInput,
    ConfirmExtractionInput,
    ExtractedItemInput,
    RecordExtractionInput,
)
from app.modules.orders import service as orders
from app.modules.orders.schemas import CreateOrderInput, OrderItemInput
from app.utils.text import normalize_text
from seed import demo_data as d
from seed.run_seed import _insert, _money, seed_id

IST = ZoneInfo("Asia/Kolkata")
DAYS = 30
SENTINEL = "bulk-order-0001"  # client_order_id of the first bulk order: present = already done

SALESMEN = {  # key -> (name, phone): 4 salesmen in total with the 2 from the main seed
    "salesman_arjun": ("Arjun Patel", "9000000005"),
    "salesman_kavita": ("Kavita Rao", "9000000006"),
}
RETIRED_SALESMEN = ["salesman_imran"]  # created by an earlier version: deactivated, history kept
ORDER_DESK = {  # 3 order desk users in total with the one from the main seed
    "order_desk_rahul": ("Rahul Mishra", "9000000008"),
    "order_desk_priya": ("Priya Saxena", "9000000009"),
}
ALL_SALESMEN = ["salesman_sunil", "salesman_deepak", *SALESMEN]
RETAILERS_PER_SALESMAN = 10
# Main-seed shops already assigned: Sunil 3 (Sharma, Gupta, Jain), Deepak 1 (Patel).
ALREADY_ASSIGNED = {"salesman_sunil": 3, "salesman_deepak": 1}
BULK_ASSIGNMENT = [k for k in ALL_SALESMEN for _ in range(RETAILERS_PER_SALESMAN - ALREADY_ASSIGNED.get(k, 0))]

NEW_CATEGORIES = ["Snacks", "Beverages", "Staples", "Personal Care"]
# (sku, name, brand, category, pack, units_per_case, base price per piece, stock cases, gst %)
NEW_PRODUCTS = [
    ("SKU-SN-200", "Masala Namkeen", "Chatpata Foods", "Snacks", "200g", 30, "38.00", 140, "12"),
    ("SKU-SN-052", "Potato Chips", "Chatpata Foods", "Snacks", "52g", 60, "17.50", 220, "12"),
    ("SKU-BV-250", "Mango Drink", "Aamras Beverages", "Beverages", "250ml", 30, "17.00", 180, "12"),
    ("SKU-BV-600", "Cola", "Fizzup", "Beverages", "600ml", 24, "33.00", 120, "28"),
    ("SKU-ST-5KG", "Chakki Atta", "Annapurna Mills", "Staples", "5kg", 4, "205.00", 90, "5"),
    ("SKU-ST-1KG", "Basmati Rice", "Annapurna Mills", "Staples", "1kg", 10, "96.00", 110, "5"),
    ("SKU-ST-DAL", "Toor Dal", "Annapurna Mills", "Staples", "1kg", 10, "128.00", 95, "5"),
    ("SKU-PC-100", "Bath Soap", "Neem Fresh", "Personal Care", "100g", 72, "24.00", 160, "18"),
    ("SKU-PC-SH6", "Shampoo Sachet", "Neem Fresh", "Personal Care", "6ml", 960, "0.95", 75, "18"),
    ("SKU-PC-TP1", "Toothpaste", "Dantmanjan", "Personal Care", "100g", 48, "42.00", 130, "18"),
    ("SKU-BS-120", "Marie Biscuit", "Sunrise Foods", "Biscuits", "120g", 48, "14.00", 200, "5"),
    ("SKU-NS-280", "Instant Noodles 4-pack", "Swaad Foods", "Noodles", "280g", 24, "44.00", 100, "5"),
]

# More products so the catalogue has 100 in total: (category code, category, name, brand,
# [(pack, units per case, base price per piece)], gst %)
_RANGE = [
    ("BS", "Biscuits", "Chocolate Cream Biscuit", "Sunrise Foods", [("75g", 96, "9.20"), ("150g", 48, "18.00")], "18"),
    ("BS", "Biscuits", "Butter Cookies", "Sunrise Foods", [("100g", 60, "22.00"), ("200g", 30, "42.00")], "18"),
    ("BS", "Biscuits", "Salted Crackers", "Crispo", [("80g", 72, "9.50"), ("160g", 36, "18.50")], "18"),
    ("BS", "Biscuits", "Digestive Biscuit", "Crispo", [("150g", 48, "24.00"), ("250g", 32, "38.00")], "18"),
    ("BS", "Biscuits", "Coconut Cookies", "Crispo", [("100g", 60, "14.50")], "18"),
    ("BS", "Biscuits", "Jeera Cookies", "Crispo", [("120g", 48, "16.00")], "18"),
    ("HC", "Home Care", "Floor Cleaner", "Dhavala Home Care", [("500ml", 24, "68.00"), ("1L", 12, "124.00")], "18"),
    ("HC", "Home Care", "Toilet Cleaner", "Dhavala Home Care", [("500ml", 24, "72.00"), ("1L", 12, "135.00")], "18"),
    ("HC", "Home Care", "Liquid Detergent", "Dhavala Home Care", [("500ml", 24, "88.00"), ("1L", 12, "165.00")], "18"),
    ("HC", "Home Care", "Dishwash Bar", "Chamak", [("140g", 72, "9.00"), ("300g", 36, "19.00")], "18"),
    ("HC", "Home Care", "Glass Cleaner", "Chamak", [("500ml", 24, "74.00")], "18"),
    ("HC", "Home Care", "Detergent Powder", "Chamak", [("2kg", 8, "198.00")], "18"),
    ("HC", "Home Care", "Mosquito Coil", "Chamak", [("10 coils", 60, "28.00")], "18"),
    ("HC", "Home Care", "Air Freshener", "Chamak", [("220ml", 24, "118.00")], "18"),
    ("TE", "Tea", "Premium Tea", "Chai Bahar", [("100g", 80, "52.00"), ("1kg", 10, "470.00")], "5"),
    ("TE", "Tea", "Green Tea Bags", "Chai Bahar", [("25 bags", 48, "88.00")], "5"),
    ("TE", "Tea", "Masala Tea", "Assam Valley", [("250g", 40, "125.00"), ("500g", 24, "240.00")], "5"),
    ("TE", "Tea", "Instant Coffee", "Brewhouse", [("50g", 48, "118.00"), ("100g", 24, "225.00")], "18"),
    ("TE", "Tea", "Filter Coffee", "Brewhouse", [("200g", 30, "145.00")], "18"),
    ("NS", "Noodles", "Atta Noodles", "Swaad Foods", [("75g", 96, "14.00")], "18"),
    ("NS", "Noodles", "Hakka Noodles", "Swaad Foods", [("150g", 60, "28.00")], "18"),
    ("NS", "Noodles", "Cup Noodles", "Swaad Foods", [("70g", 48, "38.00")], "18"),
    ("NS", "Noodles", "Vermicelli", "Annapurna Mills", [("200g", 50, "22.00"), ("400g", 25, "42.00")], "18"),
    ("NS", "Noodles", "Pasta Penne", "Annapurna Mills", [("400g", 24, "58.00")], "18"),
    ("SN", "Snacks", "Aloo Bhujia", "Chatpata Foods", [("200g", 30, "44.00"), ("400g", 20, "86.00")], "12"),
    ("SN", "Snacks", "Moong Dal Namkeen", "Chatpata Foods", [("150g", 40, "32.00")], "12"),
    ("SN", "Snacks", "Masala Peanuts", "Chatpata Foods", [("100g", 60, "18.00")], "12"),
    ("SN", "Snacks", "Corn Puffs", "Crispo", [("40g", 96, "8.50")], "12"),
    ("SN", "Snacks", "Banana Chips", "Crispo", [("150g", 40, "38.00")], "12"),
    ("SN", "Snacks", "Khakhra", "Gujarat Snacks", [("200g", 30, "52.00")], "12"),
    ("SN", "Snacks", "Mixture", "Gujarat Snacks", [("400g", 20, "78.00")], "12"),
    ("BV", "Beverages", "Lemon Drink", "Aamras Beverages", [("250ml", 30, "17.00"), ("600ml", 24, "34.00")], "12"),
    ("BV", "Beverages", "Orange Soda", "Fizzup", [("600ml", 24, "33.00"), ("2L", 9, "82.00")], "28"),
    ("BV", "Beverages", "Packaged Water", "Neer", [("500ml", 24, "8.00"), ("1L", 12, "14.00")], "18"),
    ("BV", "Beverages", "Energy Drink", "Fizzup", [("250ml", 24, "88.00")], "28"),
    ("BV", "Beverages", "Lassi", "Doodhwala", [("200ml", 30, "18.00")], "12"),
    ("BV", "Beverages", "Buttermilk", "Doodhwala", [("200ml", 30, "14.00")], "12"),
    ("ST", "Staples", "Sugar", "Annapurna Mills", [("1kg", 20, "44.00"), ("5kg", 4, "215.00")], "5"),
    ("ST", "Staples", "Iodised Salt", "Annapurna Mills", [("1kg", 25, "22.00")], "5"),
    ("ST", "Staples", "Mustard Oil", "Sarson Gold", [("1L", 12, "165.00"), ("5L", 4, "790.00")], "5"),
    ("ST", "Staples", "Sunflower Oil", "Sarson Gold", [("1L", 12, "145.00")], "5"),
    ("ST", "Staples", "Chana Dal", "Annapurna Mills", [("1kg", 10, "92.00")], "5"),
    ("ST", "Staples", "Moong Dal", "Annapurna Mills", [("1kg", 10, "118.00")], "5"),
    ("ST", "Staples", "Poha", "Annapurna Mills", [("500g", 20, "28.00")], "5"),
    ("ST", "Staples", "Besan", "Annapurna Mills", [("500g", 20, "48.00")], "5"),
    ("ST", "Staples", "Turmeric Powder", "Masala King", [("100g", 60, "24.00"), ("200g", 30, "46.00")], "5"),
    ("ST", "Staples", "Red Chilli Powder", "Masala King", [("100g", 60, "28.00"), ("200g", 30, "54.00")], "5"),
    ("ST", "Staples", "Garam Masala", "Masala King", [("50g", 96, "32.00")], "5"),
    ("PC", "Personal Care", "Hair Oil", "Neem Fresh", [("100ml", 48, "42.00"), ("200ml", 24, "80.00")], "18"),
    ("PC", "Personal Care", "Body Lotion", "Neem Fresh", [("100ml", 48, "78.00")], "18"),
    ("PC", "Personal Care", "Face Wash", "Neem Fresh", [("50g", 48, "62.00")], "18"),
    ("PC", "Personal Care", "Toothbrush", "Dantmanjan", [("1 pc", 72, "18.00")], "18"),
    ("PC", "Personal Care", "Shaving Cream", "Dantmanjan", [("70g", 48, "48.00")], "18"),
    ("PC", "Personal Care", "Laundry Soap", "Neem Fresh", [("150g", 72, "11.00")], "18"),
    ("PC", "Personal Care", "Hand Wash", "Neem Fresh", [("200ml", 24, "58.00")], "18"),
    ("PC", "Personal Care", "Talcum Powder", "Neem Fresh", [("100g", 48, "54.00")], "18"),
    ("PC", "Personal Care", "Sanitary Pads", "Neem Fresh", [("8 pcs", 48, "38.00")], "18"),
]
_stock = random.Random(100)
RANGE_PRODUCTS = [
    (f"SKU-{code}-R{n:02d}", name, brand, category, pack, units, price, _stock.randint(40, 300), gst)
    for n, (code, category, name, brand, pack, units, price, gst) in enumerate(
        (code, cat, name, brand, pack, units, price, gst)
        for code, cat, name, brand, packs, gst in _RANGE for pack, units, price in packs)
]
# (key, sku, type, min_quantity, free_quantity, discount %)
NEW_SCHEMES = [
    ("sn052_buy12_get1", "SKU-SN-052", "FREE_GOODS", "12", "1", None),
    ("bv250_10plus_5pct", "SKU-BV-250", "SLAB_DISCOUNT", "10", None, "5"),
    ("st5kg_buy20_get1", "SKU-ST-5KG", "FREE_GOODS", "20", "1", None),
    ("pc100_6plus_4pct", "SKU-PC-100", "SLAB_DISCOUNT", "6", None, "4"),
]

AREAS = ["Napier Town", "Wright Town", "Civil Lines", "Adhartal", "Ranjhi", "Gorakhpur",
         "Madan Mahal", "Gwarighat", "Vijay Nagar", "Sadar"]
FIRST = ["Rakesh", "Suresh", "Anita", "Mohan", "Pooja", "Vikas", "Seema", "Ajay", "Neha", "Rohit",
         "Kiran", "Dinesh", "Meena", "Sanjay", "Lata", "Pankaj", "Rekha", "Amit", "Usha", "Gopal"]
LAST = ["Agarwal", "Soni", "Tiwari", "Jaiswal", "Kesharwani", "Namdeo", "Dubey", "Chouksey",
        "Rajput", "Sahu"]
SHOP = ["Kirana Store", "General Store", "Provision Store", "Super Mart", "Traders"]


def _new_retailers() -> dict[str, dict]:
    """Fictional shops so every salesman has 10 (36 here + the 4 assigned in the main seed)."""
    shops = {}
    for i in range(len(BULK_ASSIGNMENT)):
        first = FIRST[i % len(FIRST)] if i < 20 else FIRST[(i * 7) % len(FIRST)]
        last = LAST[i % len(LAST)]
        key = f"bulk_{i + 1:02d}"
        shops[key] = {
            "shop_name": f"{last} {SHOP[i % len(SHOP)]}" if i < 20 else f"{last} {SHOP[(i // 10 + 2) % len(SHOP)]}, {AREAS[(i + i // 10) % len(AREAS)]}",
            "owner_name": f"{first} {last}",
            "phone": f"91000002{i + 1:02d}",
            "address": f"{10 + i * 3}, {AREAS[i % len(AREAS)]} Main Road",
            "gstin": f"23AABC{chr(65 + i)}{1000 + i}A1Z{i % 10}" if i % 3 else None,
            "salesman": BULK_ASSIGNMENT[i],
            "price_multiplier": Decimal("1.00") + Decimal(i % 5) / Decimal(100),
            "credit_limit": Decimal(150000 + (i % 4) * 50000),
            "outstanding": Decimal(5000 * (i % 6)),
        }
    return shops


def seed_master(session: Session, staff_password: str | None) -> dict[str, int]:
    admin_id = seed_id("user", "admin")
    shops = _new_retailers()
    all_products = [*d.PRODUCTS, *NEW_PRODUCTS, *RANGE_PRODUCTS]
    inserted: dict[str, int] = {}

    def add(model, rows):
        inserted[model.__tablename__] = inserted.get(model.__tablename__, 0) + _insert(session, model, rows)

    add(User, [{"id": seed_id("user", k), "name": n, "phone": p, "role": "SALESMAN"} for k, (n, p) in SALESMEN.items()])
    add(User, [{"id": seed_id("user", k), "name": n, "phone": p, "role": "ORDER_DESK"} for k, (n, p) in ORDER_DESK.items()])
    if staff_password:
        session.execute(update(User).where(User.id.in_([seed_id("user", k) for k in [*SALESMEN, *ORDER_DESK]]), User.password_hash.is_(None))
                        .values(password_hash=hash_password(staff_password)))
    session.execute(update(User).where(User.id.in_([seed_id("user", k) for k in RETIRED_SALESMEN])).values(is_active=False))
    add(Retailer, [
        {"id": seed_id("retailer", k), "shop_name": r["shop_name"], "owner_name": r["owner_name"], "phone": r["phone"],
         "address": r["address"], "city": "Jabalpur", "gstin": r["gstin"],
         "assigned_salesman_id": seed_id("user", r["salesman"])}
        for k, r in shops.items()
    ])
    add(User, [
        {"id": seed_id("user", f"retailer_{k}"), "name": r["owner_name"], "phone": r["phone"], "role": "RETAILER",
         "retailer_id": seed_id("retailer", k), "email": f"{k.replace('_', '')}@example.com"}
        for k, r in shops.items()
    ])
    add(Category, [{"id": seed_id("category", n), "name": n} for n in NEW_CATEGORIES])
    # Every bulk shop's salesman follows the 10-per-salesman plan (also for shops created earlier).
    for key, r in shops.items():
        session.execute(update(Retailer).where(Retailer.id == seed_id("retailer", key))
                        .values(assigned_salesman_id=seed_id("user", r["salesman"])))
    add(Brand, [{"id": seed_id("brand", b), "name": b}
                for b in sorted({p[2] for p in [*NEW_PRODUCTS, *RANGE_PRODUCTS]})])
    add(Product, [
        {"id": seed_id("product", sku), "sku": sku, "name": f"{name} {pack}", "brand": brand,
         "category_id": seed_id("category", cat), "pack_size": pack, "units_per_case": Decimal(per_case),
         "base_unit": d.BASE_UNIT, "order_unit": d.ORDER_UNIT, "gst_rate": Decimal(gst)}
        for sku, name, brand, cat, pack, per_case, _price, _stock, gst in [*NEW_PRODUCTS, *RANGE_PRODUCTS]
    ])
    # Every retailer (old and new) gets its own current price for every product.
    retailer_multipliers = {**{k: r["price_multiplier"] for k, r in d.RETAILERS.items()},
                            **{k: r["price_multiplier"] for k, r in shops.items()}}
    add(RetailerPrice, [
        {"id": seed_id("price", key, sku, "current"), "retailer_id": seed_id("retailer", key),
         "product_id": seed_id("product", sku), "dealer_price": _money(Decimal(price) * mult),
         "price_basis": d.DEMO_PRICE_BASIS, "tax_inclusive": d.DEMO_TAX_INCLUSIVE,
         "effective_from": d.PRICE_EFFECTIVE_FROM, "effective_to": None}
        for key, mult in retailer_multipliers.items()
        for sku, _n, _b, _c, _p, _u, price, _s, _g in all_products
    ])
    # Default price of every bulk product (retailers without their own price, e.g. new shops).
    add(RetailerPrice, [
        {"id": seed_id("price", "default", sku), "retailer_id": None, "product_id": seed_id("product", sku),
         "dealer_price": Decimal(price), "price_basis": d.DEMO_PRICE_BASIS, "tax_inclusive": d.DEMO_TAX_INCLUSIVE,
         "effective_from": d.PRICE_EFFECTIVE_FROM, "effective_to": None}
        for sku, _n, _b, _c, _p, _u, price, _s, _g in [*NEW_PRODUCTS, *RANGE_PRODUCTS]
    ])
    add(Scheme, [
        {"id": seed_id("scheme", key), "product_id": seed_id("product", sku), "scheme_type": stype,
         "min_quantity": Decimal(mq), "free_quantity": Decimal(free or 0), "discount_percentage": Decimal(pct or 0),
         "starts_at": d.SCHEME_STARTS_AT, "ends_at": None}
        for key, sku, stype, mq, free, pct in NEW_SCHEMES
    ])
    add(Inventory, [
        {"id": seed_id("inventory", sku), "product_id": seed_id("product", sku), "stock_cases": Decimal(stock)}
        for sku, _n, _b, _c, _p, _u, _price, stock, _g in [*NEW_PRODUCTS, *RANGE_PRODUCTS]
    ])
    add(StockMovement, [
        {"id": seed_id("stock_movement", sku, "opening"), "product_id": seed_id("product", sku), "movement_type": "RESTOCK",
         "quantity": Decimal(stock), "reference": "Opening stock (bulk demo)", "created_by": admin_id,
         "created_at": d.PRICE_EFFECTIVE_FROM}
        for sku, _n, _b, _c, _p, _u, _price, stock, _g in [*NEW_PRODUCTS, *RANGE_PRODUCTS]
    ])
    add(CreditAccount, [
        {"id": seed_id("credit_account", k), "retailer_id": seed_id("retailer", k),
         "credit_limit": r["credit_limit"], "current_outstanding": r["outstanding"]}
        for k, r in shops.items()
    ])
    add(CreditLedger, [
        {"id": seed_id("credit_ledger", k, "opening"), "retailer_id": seed_id("retailer", k),
         "transaction_type": "ADJUSTMENT", "amount": r["outstanding"],
         "description": "Opening outstanding balance (bulk demo)", "created_by": admin_id,
         "created_at": d.PRICE_EFFECTIVE_FROM}
        for k, r in shops.items() if r["outstanding"]
    ])
    aliases = [("bulk_01", "namkeen", "SKU-SN-200"), ("bulk_02", "chips", "SKU-SN-052"), ("bulk_03", "atta", "SKU-ST-5KG"),
               ("bulk_04", "chawal", "SKU-ST-1KG"), ("bulk_05", "dal", "SKU-ST-DAL"), ("bulk_06", "sabun", "SKU-PC-100"),
               ("bulk_07", "maaza wala", "SKU-BV-250"), ("bulk_08", "cold drink", "SKU-BV-600"),
               ("bulk_09", "marie", "SKU-BS-120"), ("bulk_10", "maggi bada", "SKU-NS-280")]
    add(RetailerAlias, [
        {"id": seed_id("alias", k, normalize_text(a)), "retailer_id": seed_id("retailer", k),
         "product_id": seed_id("product", sku), "alias": a, "normalized_alias": normalize_text(a)}
        for k, a, sku in aliases
    ])
    session.flush()
    return inserted


def seed_activity(session: Session) -> dict[str, int]:
    """~30 days of activity through the services. Skipped if already present."""
    if session.scalar(select(Order.id).where(Order.client_order_id == SENTINEL)):
        return {}
    rng = random.Random(20261105)
    desk = session.get(User, seed_id("user", "order_desk"))
    admin = session.get(User, seed_id("user", "admin"))
    products = [p for p in session.scalars(select(Product).where(Product.is_active.is_(True)))]
    retailers = list(session.scalars(select(Retailer).where(Retailer.is_active.is_(True), Retailer.assigned_salesman_id.is_not(None))))
    retailer_user = {u.retailer_id: u for u in session.scalars(select(User).where(User.role == "RETAILER", User.is_active.is_(True)))}
    by_salesman: dict[uuid.UUID, list[Retailer]] = {}
    for r in retailers:
        by_salesman.setdefault(r.assigned_salesman_id, []).append(r)

    # Generous restock first, so 30 days of orders do not run the warehouse dry.
    for inv in session.scalars(select(Inventory)):
        inv.stock_cases += Decimal(400)
        session.add(StockMovement(product_id=inv.product_id, movement_type="RESTOCK", quantity=Decimal(400),
                                  reference="Monthly purchase (bulk demo)", created_by=admin.id,
                                  created_at=datetime.now(UTC) - timedelta(days=DAYS + 1)))
    session.commit()

    counts = {"orders": 0, "visits": 0, "payments": 0, "ai_extractions": 0, "skipped": 0}
    n = 0

    def items(k: int) -> list[OrderItemInput]:
        return [OrderItemInput(product_id=p.id, quantity=Decimal(rng.choice([1, 2, 3, 5, 6, 10, 12])), unit="case")
                for p in rng.sample(products, k)]

    def when(day: int) -> datetime:
        base = datetime.now(IST).replace(hour=9, minute=30, second=0, microsecond=0) - timedelta(days=day)
        moment = base + timedelta(minutes=rng.randint(0, 9 * 60))
        return min(moment, datetime.now(IST) - timedelta(minutes=5)).astimezone(UTC)

    def backdate(order: Order, at: datetime) -> None:
        nonlocal n
        n += 1
        values = {"created_at": at, "updated_at": at, "order_number": f"DF-{at.astimezone(IST):%Y%m%d}-B{n:03d}"}
        if order.approved_at is not None:
            values["approved_at"] = at + timedelta(minutes=rng.randint(1, 90)) if order.source == "AI" else at
        session.execute(update(OrderEvent).where(OrderEvent.order_id == order.id)
                        .values(created_at=OrderEvent.created_at + (at - order.created_at)))
        if "approved_at" in values:
            session.execute(update(OrderEvent).where(OrderEvent.order_id == order.id, OrderEvent.action == "CONFIRMED")
                            .values(created_at=values["approved_at"]))
        session.execute(update(Order).where(Order.id == order.id).values(**values))
        for model in (StockMovement, CreditLedger):
            session.execute(update(model).where(model.order_id == order.id).values(created_at=values.get("approved_at", at)))
        session.commit()

    def place(actor: User, retailer: Retailer, k: int, client_id: str, day: int) -> Order | None:
        """Every order waits for the Order Desk: older ones were accepted (a few rejected);
        today's are still waiting."""
        try:
            order = orders.create_order(session, actor, CreateOrderInput(
                retailer_id=retailer.id, items=items(k), client_order_id=client_id))
        except AppException:
            counts["skipped"] += 1  # e.g. above a retailer's own credit: not placed, as in the app
            return None
        if day > 0 and order.status == "PENDING":
            try:
                if rng.random() < 0.05:
                    orders.reject_order(session, desk, order.id, "Shop closed on delivery day")
                else:
                    orders.approve_order(session, desk, order.id)
            except AppException:
                pass  # e.g. stock ran out meanwhile: it stays with the desk
            session.refresh(order)
        return order

    for day in range(DAYS, -1, -1):
        # Salesman field work: on most working days each salesman visits one of his shops
        # (today every salesman has a visit, so the salesman home shows current work).
        if (datetime.now(IST) - timedelta(days=day)).weekday() != 6:  # no field visits on Sundays
            for salesman_id, shops in by_salesman.items():
                if day and rng.random() > 0.75:
                    continue
                salesman = session.get(User, salesman_id)
                for shop in rng.sample(shops, 1):
                    start = when(day)
                    order = None
                    if rng.random() < 0.65:
                        cid = SENTINEL if counts["orders"] == 0 else f"bulk-sm-{day:02d}-{shop.id.hex[:8]}-{n}"
                        order = place(salesman, shop, rng.randint(1, 4), cid, day)
                        if order is not None:
                            backdate(order, start + timedelta(minutes=8))
                            counts["orders"] += 1
                    session.add(ShopVisit(
                        id=uuid.uuid5(uuid.NAMESPACE_URL, f"bulk-visit-{day}-{shop.id}-{counts['visits']}"),
                        salesman_id=salesman_id, retailer_id=shop.id, started_at=start,
                        ended_at=start + timedelta(minutes=rng.randint(10, 35)),
                        outcome="ORDER_PLACED" if order else "NO_ORDER", order_id=order.id if order else None,
                    ))
                    session.commit()
                    counts["visits"] += 1

        # Retailers ordering from the catalogue themselves (reviewed by the Order Desk).
        for shop in rng.sample(retailers, 1 if rng.random() < 0.9 else 0):
            user = retailer_user.get(shop.id)
            if user is None:
                continue
            order = place(user, shop, rng.randint(1, 3), f"bulk-rt-{day:02d}-{shop.id.hex[:8]}", day)
            if order is not None:
                backdate(order, when(day))
                counts["orders"] += 1

        # Messages captured by AI every few days: desk confirms most, rejects some, a few wait.
        if day % 3 == 0:
            shop = rng.choice([r for r in retailers if r.id in retailer_user])
            user = retailer_user[shop.id]
            picked = rng.sample(products, 2)
            extraction = ai_orders.record_extraction(session, user, RecordExtractionInput(
                original_message=" aur ".join(f"{rng.randint(1, 4)} peti {p.name.lower()}" for p in picked),
                model_name="bulk-demo (no LLM call)",
                items=[ExtractedItemInput(original_text=f"{p.name.lower()}", extracted_name=p.name.lower(),
                                          quantity=Decimal(rng.randint(1, 4)), unit="case", matched_product_id=p.id,
                                          confidence=Decimal("0.900")) for p in picked],
            ))
            counts["ai_extractions"] += 1
            try:
                order = ai_orders.confirm_extraction(session, user, extraction.id, ConfirmExtractionInput(items=[
                    ConfirmedItemInput(extraction_item_id=i.id, product_id=i.matched_product_id, quantity=i.quantity, unit="case")
                    for i in extraction.items]))
            except AppException:
                counts["skipped"] += 1
                order = None
            if order is not None:
                fate = rng.random()
                if day > 1 and fate < 0.6:
                    try:
                        orders.approve_order(session, desk, order.id)
                    except AppException:
                        pass  # stays on credit hold, as in the app
                elif day > 1 and fate < 0.8:
                    orders.reject_order(session, desk, order.id, rng.choice(
                        ["Duplicate of a phone order", "Retailer cancelled", "Wrong product in message"]))
                backdate(session.get(Order, order.id), when(day))
                counts["orders"] += 1

        # Payments collected every few days.
        if day % 3 == 1:
            for shop in rng.sample(retailers, 3):
                account = session.scalar(select(CreditAccount).where(CreditAccount.retailer_id == shop.id))
                if account is None or account.current_outstanding <= 0:
                    continue
                amount = min(account.current_outstanding, Decimal(rng.choice([5000, 8000, 10000, 15000])))
                account.current_outstanding -= amount
                session.add(CreditLedger(retailer_id=shop.id, transaction_type="PAYMENT_CREDIT", amount=-amount,
                                         description="Payment received (bulk demo)", created_by=admin.id,
                                         created_at=when(day)))
                session.commit()
                counts["payments"] += 1
    return counts


def check_balances(session: Session) -> None:
    """Stock = sum of stock movements per product; outstanding = sum of ledger per retailer."""
    from sqlalchemy import func

    moved = dict(session.execute(select(StockMovement.product_id, func.sum(StockMovement.quantity)).group_by(StockMovement.product_id)).all())
    for inv in session.scalars(select(Inventory)):
        assert inv.stock_cases == moved.get(inv.product_id, 0), f"stock mismatch for {inv.product_id}"
        assert inv.stock_cases >= 0
    ledger = dict(session.execute(select(CreditLedger.retailer_id, func.sum(CreditLedger.amount)).group_by(CreditLedger.retailer_id)).all())
    for account in session.scalars(select(CreditAccount)):
        assert account.current_outstanding == ledger.get(account.retailer_id, 0), f"credit mismatch for {account.retailer_id}"


def main() -> None:
    from app.database.session import SessionLocal

    parser = argparse.ArgumentParser(description="Add fuller demo data (development only).")
    parser.add_argument("--staff-password", help="password for the new demo salesmen (stored hashed)")
    args = parser.parse_args()
    with SessionLocal() as session:
        master = seed_master(session, args.staff_password)
        session.commit()
        activity = seed_activity(session)
        check_balances(session)
    print("master rows inserted:", {k: v for k, v in master.items() if v})
    print("activity:", activity or "already present, nothing added")


if __name__ == "__main__":
    main()
