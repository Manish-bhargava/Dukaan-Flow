"""Retailer catalogue: active products the retailer has a current dealer price for, with
that retailer's price, current stock and active schemes. Prices come only from the
backend; another retailer's prices are never returned.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.constants import ErrorCode, PriceBasis
from app.exceptions.base import AppException
from app.models import Category, User
from app.modules.pricing import repository as pricing_repository
from app.modules.pricing.service import money
from app.modules.products import repository
from app.modules.products.schemas import CategoryOut, PriceOut, ProductOut, ProductPageOut, SchemeOut
from app.modules.retailers import service as retailers_service


def list_categories(db: Session) -> list[Category]:
    return repository.list_active_categories(db)


def list_catalogue(
    db: Session,
    actor: User,
    search: str | None = None,
    category_id: uuid.UUID | None = None,
    page: int = 1,
    limit: int = 20,
) -> ProductPageOut:
    if actor.retailer_id is None:
        raise AppException("No retailer is linked to this account", ErrorCode.FORBIDDEN, 403)
    retailer = retailers_service.get_retailer_for(db, actor, actor.retailer_id)

    now = datetime.now(UTC)
    prices = pricing_repository.get_effective_prices(db, retailer.id, now)
    products, total = repository.list_products(
        db, prices.keys(), search.strip() if search else None, category_id, (page - 1) * limit, limit
    )
    ids = [p.id for p in products]
    stock = repository.get_stock(db, ids)
    schemes = pricing_repository.get_active_schemes(db, now, ids)

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
                image_url=product.image_url,
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
                        scheme_type=s.scheme_type,
                        min_quantity=s.min_quantity,
                        free_quantity=s.free_quantity,
                        discount_percentage=s.discount_percentage,
                    )
                    for s in schemes.get(product.id, [])
                ],
            )
        )
    return ProductPageOut(items=items, page=page, limit=limit, total=total)
