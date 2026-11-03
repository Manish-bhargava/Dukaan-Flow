import uuid
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import RetailerPrice, Scheme


def get_effective_prices(
    db: Session,
    retailer_id: uuid.UUID,
    at: datetime,
    product_ids: Iterable[uuid.UUID] | None = None,
) -> dict[uuid.UUID, RetailerPrice]:
    """The retailer's price per product effective at `at` (latest effective_from wins)."""
    statement = (
        select(RetailerPrice)
        .where(
            RetailerPrice.retailer_id == retailer_id,
            RetailerPrice.effective_from <= at,
            or_(RetailerPrice.effective_to.is_(None), RetailerPrice.effective_to > at),
        )
        .distinct(RetailerPrice.product_id)
        .order_by(RetailerPrice.product_id, RetailerPrice.effective_from.desc())
    )
    if product_ids is not None:
        statement = statement.where(RetailerPrice.product_id.in_(list(product_ids)))
    return {price.product_id: price for price in db.scalars(statement)}


def get_active_schemes(
    db: Session, at: datetime, product_ids: Iterable[uuid.UUID] | None = None
) -> dict[uuid.UUID, list[Scheme]]:
    """Active schemes whose date window includes `at`, grouped by product."""
    statement = (
        select(Scheme)
        .where(
            Scheme.is_active.is_(True),
            Scheme.starts_at <= at,
            or_(Scheme.ends_at.is_(None), Scheme.ends_at > at),
        )
        .order_by(Scheme.min_quantity)
    )
    if product_ids is not None:
        statement = statement.where(Scheme.product_id.in_(list(product_ids)))
    schemes: dict[uuid.UUID, list[Scheme]] = {}
    for scheme in db.scalars(statement):
        schemes.setdefault(scheme.product_id, []).append(scheme)
    return schemes
