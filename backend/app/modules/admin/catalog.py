"""Admin: categories, brands, products, prices, schemes and stock.

The one product catalogue used by retailers, salesmen and the Order Desk. Prices and schemes
changed here apply to new orders only; placed orders keep their snapshots. Every change is
audited; stock changes are also stock movements (with the stock after each).
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.constants import ErrorCode, PriceBasis, StockMovementType, UserRole
from app.core.permissions import ensure_role
from app.exceptions.base import AppException
from app.models import Brand, Category, Inventory, Product, RetailerPrice, Scheme, StockMovement, User
from app.modules.admin import repository
from app.modules.admin.people import _committed, _conflict, _not_found, _retailer
from app.modules.admin.schemas import (
    NamedCreate,
    NamedUpdate,
    PriceInput,
    PriceSet,
    ProductCreate,
    ProductUpdate,
    SchemeCreate,
    SchemeUpdate,
    StockAdjust,
)
from app.modules.audit.service import changes, record
from app.modules.schemes import engine as schemes_engine
from app.modules.settings.service import get_settings


# ---------------------------------------------------------------- categories and brands


def list_categories(db: Session, actor: User):
    ensure_role(actor, UserRole.ADMIN)
    return repository.categories_with_counts(db)


def create_category(db: Session, actor: User, data: NamedCreate) -> Category:
    ensure_role(actor, UserRole.ADMIN)

    def work():
        category = Category(name=data.name.strip())
        db.add(category)
        db.flush()
        record(db, actor, "CATEGORY_CREATED", "category", category.id, category.name)
        return category

    return _committed(db, work)


def update_category(db: Session, actor: User, category_id: uuid.UUID, data: NamedUpdate) -> Category:
    """Deactivating a category hides its products from every catalogue (they stay on orders)."""
    ensure_role(actor, UserRole.ADMIN)

    def work():
        category = db.get(Category, category_id)
        if category is None:
            raise _not_found("Category", category_id)
        before = {"name": category.name, "is_active": category.is_active}
        if data.name:
            category.name = data.name.strip()
        if data.is_active is not None:
            category.is_active = data.is_active
        diff = changes(before, {"name": category.name, "is_active": category.is_active})
        if diff:
            record(db, actor, "CATEGORY_UPDATED", "category", category.id, category.name, {"changes": diff})
        return category

    return _committed(db, work)


def list_brands(db: Session, actor: User):
    ensure_role(actor, UserRole.ADMIN)
    return repository.brands_with_counts(db)


def create_brand(db: Session, actor: User, data: NamedCreate) -> Brand:
    ensure_role(actor, UserRole.ADMIN)

    def work():
        brand = Brand(name=data.name.strip())
        db.add(brand)
        db.flush()
        record(db, actor, "BRAND_CREATED", "brand", brand.id, brand.name)
        return brand

    return _committed(db, work)


def update_brand(db: Session, actor: User, brand_id: uuid.UUID, data: NamedUpdate) -> Brand:
    """Renaming a brand renames it on its products (foreign key ON UPDATE CASCADE). An
    inactive brand cannot be chosen for products; existing products keep it."""
    ensure_role(actor, UserRole.ADMIN)

    def work():
        brand = db.get(Brand, brand_id)
        if brand is None:
            raise _not_found("Brand", brand_id)
        before = {"name": brand.name, "is_active": brand.is_active}
        if data.name:
            brand.name = data.name.strip()
        if data.is_active is not None:
            brand.is_active = data.is_active
        db.flush()
        diff = changes(before, {"name": brand.name, "is_active": brand.is_active})
        if diff:
            record(db, actor, "BRAND_UPDATED", "brand", brand.id, brand.name, {"changes": diff})
        db.expire_all()  # products see the cascaded name
        return brand

    return _committed(db, work)


# ---------------------------------------------------------------- products


def _product(db: Session, product_id: uuid.UUID) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise _not_found("Product", product_id)
    return product


def _active_brand(db: Session, name: str) -> str:
    brand = db.query(Brand).filter(Brand.name == name.strip()).one_or_none()
    if brand is None:
        raise AppException(f"Unknown brand '{name}'; add it under Categories & brands first", ErrorCode.VALIDATION_ERROR, 422)
    if not brand.is_active:
        raise _conflict(f"Brand '{brand.name}' is inactive")
    return brand.name


def _category(db: Session, category_id: uuid.UUID) -> Category:
    category = db.get(Category, category_id)
    if category is None:
        raise _not_found("Category", category_id)
    return category


def _product_snapshot(p: Product) -> dict:
    return {k: getattr(p, k) for k in ("sku", "name", "brand", "category_id", "pack_size", "units_per_case",
                                       "base_unit", "order_unit", "gst_rate", "is_active")}


def list_products(db: Session, actor: User, *, search, category_id, brand, status, stock, page, limit):
    ensure_role(actor, UserRole.ADMIN)
    cfg = get_settings(db)
    rows, total = repository.search_products(
        db, search=(search or "").strip() or None, category_id=category_id, brand=brand, status=status, stock=stock,
        low_stock=cfg.low_stock_cases, offset=(page - 1) * limit, limit=limit)
    now = datetime.now(UTC)
    ids = [p.id for p, _ in rows]
    return {"rows": rows, "total": total, "defaults": repository.default_prices(db, now, ids),
            "overrides": repository.override_counts(db, now), "low_stock": cfg.low_stock_cases}


def create_product(db: Session, actor: User, data: ProductCreate) -> Product:
    """Product + inventory row (opening stock as a RESTOCK movement) + optional default price."""
    ensure_role(actor, UserRole.ADMIN)

    def work():
        category = _category(db, data.category_id)
        if repository.count(db, Product, Product.sku == data.sku.strip().upper()):
            raise _conflict(f"SKU {data.sku.upper()} already exists", field="sku")
        product = Product(sku=data.sku.strip().upper(), name=data.name.strip(), brand=_active_brand(db, data.brand),
                          category_id=category.id, pack_size=data.pack_size.strip(), units_per_case=data.units_per_case,
                          base_unit=data.base_unit.strip(), order_unit=data.order_unit.strip(), gst_rate=data.gst_rate)
        db.add(product)
        db.flush()
        db.add(Inventory(product_id=product.id, stock_cases=data.opening_stock))
        if data.opening_stock > 0:
            db.add(StockMovement(product_id=product.id, movement_type=StockMovementType.RESTOCK,
                                 quantity=data.opening_stock, stock_after=data.opening_stock,
                                 reference="Opening stock", created_by=actor.id))
        record(db, actor, "PRODUCT_CREATED", "product", product.id, f"{product.name} ({product.sku})",
               {"after": {**_product_snapshot(product), "opening_stock": data.opening_stock}})
        if data.default_price:
            _set_price(db, actor, product, None, data.default_price)
        return product

    return _committed(db, work)


def get_product(db: Session, actor: User, product_id: uuid.UUID) -> dict:
    ensure_role(actor, UserRole.ADMIN)
    product = _product(db, product_id)
    now = datetime.now(UTC)
    schemes, _ = repository.schemes(db, product_search=None, product_id=product.id, state="all", now=now, offset=0, limit=50)
    return {
        "product": product,
        "stock": product.inventory.stock_cases if product.inventory else Decimal(0),
        "stock_updated_at": product.inventory.updated_at if product.inventory else None,
        "default_price": repository.default_prices(db, now, [product.id]).get(product.id),
        "price_history": repository.price_history(db, product.id),
        "schemes": schemes,
        "movements": repository.stock_history(db, product.id, 20),
        "low_stock": get_settings(db).low_stock_cases,
    }


def update_product(db: Session, actor: User, product_id: uuid.UUID, data: ProductUpdate) -> Product:
    """Edits apply to new orders; placed orders keep their product/price snapshots.
    Deactivated products disappear from catalogues and cannot be ordered or confirmed."""
    ensure_role(actor, UserRole.ADMIN)
    fields = data.model_fields_set

    def work():
        product = _product(db, product_id)
        before = _product_snapshot(product)
        if "sku" in fields and data.sku and data.sku.strip().upper() != product.sku:
            sku = data.sku.strip().upper()
            if repository.count(db, Product, Product.sku == sku):
                raise _conflict(f"SKU {sku} already exists", field="sku")
            product.sku = sku
        if "brand" in fields and data.brand and data.brand.strip() != product.brand:
            product.brand = _active_brand(db, data.brand)
        if "category_id" in fields and data.category_id:
            product.category_id = _category(db, data.category_id).id
        for name in ("name", "pack_size", "base_unit", "order_unit"):
            if name in fields and getattr(data, name):
                setattr(product, name, getattr(data, name).strip())
        for name in ("units_per_case", "gst_rate", "is_active"):
            if name in fields and getattr(data, name) is not None:
                setattr(product, name, getattr(data, name))
        diff = changes(before, _product_snapshot(product))
        if diff:
            action = ("PRODUCT_DEACTIVATED" if diff.get("is_active", {}).get("to") is False else
                      "PRODUCT_ACTIVATED" if diff.get("is_active", {}).get("to") is True else "PRODUCT_UPDATED")
            record(db, actor, action, "product", product.id, f"{product.name} ({product.sku})", {"changes": diff})
        return product

    return _committed(db, work)


# ---------------------------------------------------------------- prices


def _set_price(db: Session, actor: User, product: Product, retailer_id: uuid.UUID | None, data: PriceInput) -> RetailerPrice:
    """Close the current price of this scope (default or one retailer) and start a new one now.
    Old rows stay as the price history; orders already placed keep their snapshot."""
    now = datetime.now(UTC)
    current = repository.current_price_row(db, product.id, retailer_id, now, lock=True)
    if current is not None and (current.dealer_price, current.price_basis, current.tax_inclusive) == (
            data.dealer_price, data.price_basis, data.tax_inclusive):
        return current
    if current is not None:
        current.effective_to = now
    price = RetailerPrice(product_id=product.id, retailer_id=retailer_id, dealer_price=data.dealer_price,
                          price_basis=data.price_basis, tax_inclusive=data.tax_inclusive,
                          effective_from=now, effective_to=None, created_by=actor.id)
    db.add(price)
    db.flush()
    label = f"{product.name} ({product.sku})"
    scope = "default price"
    if retailer_id is not None:
        scope = f"price for {_retailer(db, retailer_id).shop_name}"
    record(db, actor, "PRICE_CHANGED", "price", product.id, label, {
        "scope": scope, "retailer_id": retailer_id,
        "from": {"dealer_price": current.dealer_price, "price_basis": current.price_basis,
                 "tax_inclusive": current.tax_inclusive} if current else None,
        "to": {"dealer_price": data.dealer_price, "price_basis": data.price_basis, "tax_inclusive": data.tax_inclusive},
    })
    return price


def set_price(db: Session, actor: User, data: PriceSet) -> RetailerPrice:
    ensure_role(actor, UserRole.ADMIN)

    def work():
        product = _product(db, data.product_id)
        if data.retailer_id is not None:
            _retailer(db, data.retailer_id)
        return _set_price(db, actor, product, data.retailer_id, data)

    return _committed(db, work)


def remove_retailer_price(db: Session, actor: User, product_id: uuid.UUID, retailer_id: uuid.UUID) -> None:
    """End a retailer-specific price: the retailer gets the default price again (if there is
    one; otherwise the product leaves their catalogue)."""
    ensure_role(actor, UserRole.ADMIN)

    def work():
        product = _product(db, product_id)
        retailer = _retailer(db, retailer_id)
        now = datetime.now(UTC)
        current = repository.current_price_row(db, product.id, retailer.id, now, lock=True)
        if current is None:
            raise _not_found("Retailer price", product_id)
        current.effective_to = now
        record(db, actor, "PRICE_REMOVED", "price", product.id, f"{product.name} ({product.sku})", {
            "scope": f"price for {retailer.shop_name}", "retailer_id": retailer.id,
            "from": {"dealer_price": current.dealer_price, "price_basis": current.price_basis}})

    return _committed(db, work)


def retailer_prices(db: Session, actor: User, retailer_id: uuid.UUID) -> list[dict]:
    """Every active product with the default price, the retailer's own price and the active
    schemes (schemes are per product, the same for every retailer)."""
    ensure_role(actor, UserRole.ADMIN)
    retailer = _retailer(db, retailer_id)
    now = datetime.now(UTC)
    defaults = repository.default_prices(db, now)
    own = repository.own_prices(db, retailer.id, now)
    from app.modules.pricing import repository as pricing_repository

    schemes = pricing_repository.get_active_schemes(db, now)
    products, _ = repository.search_products(db, search=None, category_id=None, brand=None, status="active", stock=None,
                                             low_stock=0, offset=0, limit=1000)
    return [{"product": p, "default": defaults.get(p.id), "own": own.get(p.id),
             "schemes": [schemes_engine.describe(s) for s in schemes.get(p.id, [])]} for p, _ in products]


# ---------------------------------------------------------------- schemes


def scheme_state(scheme: Scheme, now: datetime) -> str:
    if not scheme.is_active:
        return "inactive"
    if scheme.ends_at is not None and scheme.ends_at <= now:
        return "expired"
    if scheme.starts_at > now:
        return "upcoming"
    return "active"


def _ensure_no_overlap(db: Session, scheme: Scheme) -> None:
    """Schemes are never combined (the engine refuses a line where two qualify), so a product
    may have only one active scheme at any time."""
    if not scheme.is_active:
        return
    clash = repository.overlapping_schemes(db, scheme.product_id, scheme.starts_at, scheme.ends_at, scheme.id)
    if clash:
        product = db.get(Product, scheme.product_id)
        raise AppException(
            f"{product.sku} already has an active scheme in these dates ({schemes_engine.describe(clash[0])}); "
            "end or deactivate it first",
            ErrorCode.SCHEME_CONFLICT, 409, {"product_id": str(scheme.product_id), "scheme_ids": [str(c.id) for c in clash]},
        )


def _scheme_snapshot(s: Scheme) -> dict:
    return {"description": schemes_engine.describe(s), "min_quantity": s.min_quantity, "free_quantity": s.free_quantity,
            "discount_percentage": s.discount_percentage, "starts_at": s.starts_at, "ends_at": s.ends_at,
            "is_active": s.is_active}


def list_schemes(db: Session, actor: User, *, search, product_id, state, page, limit):
    ensure_role(actor, UserRole.ADMIN)
    if state not in ("all", "active", "upcoming", "expired", "inactive"):
        raise AppException("Unknown state", ErrorCode.VALIDATION_ERROR, 422)
    return repository.schemes(db, product_search=(search or "").strip() or None, product_id=product_id, state=state,
                              now=datetime.now(UTC), offset=(page - 1) * limit, limit=limit)


def create_schemes(db: Session, actor: User, data: SchemeCreate) -> list[Scheme]:
    """One scheme per eligible product (a scheme belongs to one product)."""
    ensure_role(actor, UserRole.ADMIN)

    def work():
        created = []
        for product_id in dict.fromkeys(data.product_ids):
            product = _product(db, product_id)
            scheme = Scheme(product_id=product.id, scheme_type=data.scheme_type, min_quantity=data.min_quantity,
                            free_quantity=data.free_quantity, discount_percentage=data.discount_percentage,
                            starts_at=data.starts_at, ends_at=data.ends_at, is_active=True)
            _ensure_no_overlap(db, scheme)
            db.add(scheme)
            db.flush()
            record(db, actor, "SCHEME_CREATED", "scheme", scheme.id, f"{product.sku}: {schemes_engine.describe(scheme)}",
                   {"after": _scheme_snapshot(scheme)})
            created.append(scheme)
        return created

    return _committed(db, work)


def update_scheme(db: Session, actor: User, scheme_id: uuid.UUID, data: SchemeUpdate) -> Scheme:
    """Applies to orders priced from now on; placed orders keep their scheme snapshot."""
    ensure_role(actor, UserRole.ADMIN)
    fields = data.model_fields_set

    def work():
        scheme = db.get(Scheme, scheme_id)
        if scheme is None:
            raise _not_found("Scheme", scheme_id)
        before = _scheme_snapshot(scheme)
        if "min_quantity" in fields and data.min_quantity is not None:
            scheme.min_quantity = data.min_quantity
        if "free_quantity" in fields and data.free_quantity is not None:
            scheme.free_quantity = data.free_quantity
        if "discount_percentage" in fields and data.discount_percentage is not None:
            scheme.discount_percentage = data.discount_percentage
        if "starts_at" in fields and data.starts_at is not None:
            scheme.starts_at = data.starts_at
        if "ends_at" in fields:
            scheme.ends_at = data.ends_at
        if "is_active" in fields and data.is_active is not None:
            scheme.is_active = data.is_active
        if scheme.ends_at is not None and scheme.ends_at <= scheme.starts_at:
            raise AppException("The end must be after the start", ErrorCode.VALIDATION_ERROR, 422)
        if (scheme.scheme_type == "FREE_GOODS" and scheme.free_quantity <= 0) or (
                scheme.scheme_type == "SLAB_DISCOUNT" and scheme.discount_percentage <= 0):
            raise AppException("The scheme's benefit must be above 0", ErrorCode.VALIDATION_ERROR, 422)
        _ensure_no_overlap(db, scheme)
        diff = changes(before, _scheme_snapshot(scheme))
        if diff:
            record(db, actor, "SCHEME_UPDATED", "scheme", scheme.id,
                   f"{scheme.product.sku}: {schemes_engine.describe(scheme)}", {"changes": diff})
        return scheme

    return _committed(db, work)


# ---------------------------------------------------------------- stock


def list_stock(db: Session, actor: User, *, search, category_id, stock, page, limit):
    ensure_role(actor, UserRole.ADMIN)
    cfg = get_settings(db)
    rows, total = repository.search_products(
        db, search=(search or "").strip() or None, category_id=category_id, brand=None, status=None, stock=stock,
        low_stock=cfg.low_stock_cases, offset=(page - 1) * limit, limit=limit)
    return {"rows": rows, "total": total, "last_movement": repository.last_movements(db, [p.id for p, _ in rows]),
            "low_stock": cfg.low_stock_cases}


def adjust_stock(db: Session, actor: User, product_id: uuid.UUID, data: StockAdjust) -> StockMovement:
    """Add (restock), remove (damage, loss) or set (stock count) with a reason. Recorded as a
    stock movement with the stock before/after, and in the audit log. Stock never goes
    below 0 (confirmed orders have already taken theirs)."""
    ensure_role(actor, UserRole.ADMIN)

    def work():
        product = _product(db, product_id)
        inventory = repository.lock_inventory_row(db, product.id)
        if inventory is None:
            inventory = Inventory(product_id=product.id, stock_cases=Decimal(0))
            db.add(inventory)
            db.flush()
        previous = inventory.stock_cases
        new = {"add": previous + data.quantity, "remove": previous - data.quantity,
               "set": data.quantity}[data.mode].quantize(Decimal("0.001"))
        if new < 0:
            raise AppException(f"Only {previous.normalize():f} cases in stock; cannot remove {data.quantity.normalize():f}",
                               ErrorCode.VALIDATION_ERROR, 422)
        change = (new - previous).quantize(Decimal("0.001"))
        if change == 0:
            raise AppException("The stock would not change", ErrorCode.VALIDATION_ERROR, 422)
        inventory.stock_cases = new
        movement = StockMovement(
            product_id=product.id,
            movement_type=StockMovementType.RESTOCK if data.mode == "add" else StockMovementType.ADJUSTMENT,
            quantity=change, stock_after=new, reference=data.reason.strip()[:200], created_by=actor.id,
            created_at=datetime.now(UTC))
        db.add(movement)
        record(db, actor, "STOCK_CHANGED", "stock", product.id, f"{product.name} ({product.sku})",
               {"mode": data.mode, "previous": previous, "new": new, "change": change, "reason": data.reason.strip()})
        return movement

    return _committed(db, work)


def stock_history(db: Session, actor: User, product_id: uuid.UUID):
    ensure_role(actor, UserRole.ADMIN)
    _product(db, product_id)
    return repository.stock_history(db, product_id)


PRICE_BASES = [b.value for b in PriceBasis]
