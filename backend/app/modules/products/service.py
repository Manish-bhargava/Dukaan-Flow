"""Retailer catalogue: active products the retailer has a current dealer price for, with
that retailer's price, current stock and active schemes. Prices come only from the
backend; another retailer's prices are never returned.

Retailers always get their own catalogue. Staff must name a retailer they may access
(SALESMAN: assigned shops; ORDER_DESK/ADMIN: any), e.g. to correct an order's product.
"""

import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.constants import ErrorCode, PriceBasis, UserRole
from app.core.config import settings
from app.core.permissions import ensure_role, forbidden
from app.exceptions.base import AppException
from app.models import Category, Product, Retailer, User
from app.modules.pricing import repository as pricing_repository
from app.modules.pricing.service import money
from app.modules.products import images, repository
from app.modules.products.schemas import (
    CategoryOut,
    PriceOut,
    ProductImageOut,
    ProductOut,
    ProductPageOut,
    SchemeOut,
)
from app.modules.retailers import service as retailers_service
from app.modules.schemes import engine as schemes_engine


def list_categories(db: Session) -> list[Category]:
    return repository.list_active_categories(db)


def _retailer_for(db: Session, actor: User, retailer_id: uuid.UUID | None) -> Retailer:
    """Retailers: their own shop. Staff: the named retailer, if they may access it."""
    if actor.role == UserRole.RETAILER:
        if actor.retailer_id is None:
            raise AppException("No retailer is linked to this account", ErrorCode.FORBIDDEN, 403)
        if retailer_id is not None and retailer_id != actor.retailer_id:
            raise forbidden("You can only see your own prices")
        retailer_id = actor.retailer_id
    elif retailer_id is None:
        raise AppException("retailer_id is required", ErrorCode.VALIDATION_ERROR, 422)
    return retailers_service.get_retailer_for(db, actor, retailer_id)


def _product_outs(db: Session, products: list[Product], prices: dict, now: datetime) -> list[ProductOut]:
    ids = [p.id for p in products]
    stock = repository.get_stock(db, ids)
    schemes = pricing_repository.get_active_schemes(db, now, ids)  # active + in date window
    items = []
    for product in products:
        price = prices[product.id]
        case_price = (
            price.dealer_price * product.units_per_case
            if price.price_basis == PriceBasis.PIECE
            else price.dealer_price
        )
        stock_cases = stock.get(product.id, Decimal("0"))
        items.append(
            ProductOut(
                id=product.id,
                sku=product.sku,
                name=product.name,
                brand=product.brand,
                category=CategoryOut(id=product.category.id, name=product.category.name),
                pack_size=product.pack_size,
                units_per_case=product.units_per_case,
                base_unit=product.base_unit,
                order_unit=product.order_unit,
                gst_rate=product.gst_rate,
                image_url=images.delivery_url(product.image_url, images.LARGE),
                thumbnail_url=images.delivery_url(product.image_url, images.THUMBNAIL),
                price=PriceOut(
                    dealer_price=price.dealer_price,
                    price_basis=price.price_basis,
                    tax_inclusive=price.tax_inclusive,
                    case_price=money(case_price),
                ),
                stock_cases=stock_cases,
                in_stock=stock_cases > 0,
                schemes=[
                    SchemeOut(
                        id=s.id,
                        description=schemes_engine.describe(s),
                        scheme_type=s.scheme_type,
                        min_quantity=s.min_quantity,
                        free_quantity=s.free_quantity,
                        discount_percentage=s.discount_percentage,
                    )
                    for s in schemes.get(product.id, [])
                ],
            )
        )
    return items


def list_catalogue(
    db: Session,
    actor: User,
    search: str | None = None,
    category_id: uuid.UUID | None = None,
    page: int = 1,
    limit: int = 20,
    retailer_id: uuid.UUID | None = None,
    has_scheme: bool = False,
) -> ProductPageOut:
    """`has_scheme`: only products with a scheme active now (the Offers & Schemes view)."""
    retailer = _retailer_for(db, actor, retailer_id)
    now = datetime.now(UTC)
    prices = pricing_repository.get_effective_prices(db, retailer.id, now)
    candidates = set(prices.keys())
    if has_scheme:
        candidates &= set(pricing_repository.get_active_schemes(db, now).keys())
    products, total = repository.list_products(
        db, candidates, search.strip() if search else None, category_id, (page - 1) * limit, limit
    )
    return ProductPageOut(items=_product_outs(db, products, prices, now), page=page, limit=limit, total=total)


def get_catalogue_product(
    db: Session, actor: User, product_id: uuid.UUID, retailer_id: uuid.UUID | None = None
) -> ProductOut:
    """One product of the retailer's catalogue (404 if inactive or not priced for them)."""
    retailer = _retailer_for(db, actor, retailer_id)
    now = datetime.now(UTC)
    prices = pricing_repository.get_effective_prices(db, retailer.id, now, [product_id])
    products, _ = repository.list_products(db, prices.keys(), None, None, 0, 1)
    if not products:
        raise AppException("Product not found", ErrorCode.PRODUCT_NOT_FOUND, 404, {"product_id": str(product_id)})
    return _product_outs(db, products, prices, now)[0]


def upload_product_image(
    db: Session, actor: User, product_id: uuid.UUID, content: bytes, content_type: str | None
) -> ProductImageOut:
    """ADMIN: upload (or replace) a product's image on Cloudinary and store its URL and public_id."""
    ensure_role(actor, UserRole.ADMIN)
    product = repository.get_product(db, product_id)
    if product is None:
        raise AppException("Product not found", ErrorCode.PRODUCT_NOT_FOUND, 404, {"product_id": str(product_id)})
    images.validate(content, content_type)
    public_id = f"{settings.CLOUDINARY_FOLDER.strip('/')}/{re.sub(r'[^a-z0-9_-]', '-', product.sku.lower())}"
    try:
        stored = images.upload(content, content_type or "", public_id)
        product.image_url = stored.secure_url
        product.image_public_id = stored.public_id
        db.commit()
    except Exception:
        db.rollback()
        raise
    return ProductImageOut(
        product_id=product.id,
        image_public_id=stored.public_id,
        image_url=images.delivery_url(stored.secure_url, images.LARGE),
        thumbnail_url=images.delivery_url(stored.secure_url, images.THUMBNAIL),
    )
