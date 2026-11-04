import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from app.models import AiExtraction, Category, Order, OrderItem, Product, RetailerAlias
from app.utils.text import normalize_text


def get_extraction(db: Session, extraction_id: uuid.UUID, lock: bool = False) -> AiExtraction | None:
    statement = (
        select(AiExtraction)
        .where(AiExtraction.id == extraction_id)
        .options(selectinload(AiExtraction.items))
    )
    if lock:
        statement = statement.with_for_update(of=AiExtraction).execution_options(
            populate_existing=True
        )
    return db.scalar(statement)


def save_alias(db: Session, retailer_id: uuid.UUID, product_id: uuid.UUID, alias: str) -> None:
    """Create or re-point the retailer's alias (unique per retailer + normalized text)."""
    statement = insert(RetailerAlias).values(
        retailer_id=retailer_id,
        product_id=product_id,
        alias=alias,
        normalized_alias=normalize_text(alias),
    )
    db.execute(
        statement.on_conflict_do_update(
            index_elements=[RetailerAlias.retailer_id, RetailerAlias.normalized_alias],
            set_={"product_id": statement.excluded.product_id, "alias": statement.excluded.alias},
        )
    )


def get_aliases(db: Session, retailer_id: uuid.UUID) -> list[RetailerAlias]:
    return list(db.scalars(select(RetailerAlias).where(RetailerAlias.retailer_id == retailer_id)))


def get_catalogue(db: Session, product_ids: list[uuid.UUID]) -> list[tuple[Product, str]]:
    """Active products (with category name) among `product_ids`."""
    statement = (
        select(Product, Category.name)
        .join(Product.category)
        .where(Product.id.in_(product_ids), Product.is_active.is_(True), Category.is_active.is_(True))
        .order_by(Product.sku)
    )
    return [(product, category) for product, category in db.execute(statement).tuples()]


def get_recent_product_ids(db: Session, retailer_id: uuid.UUID, orders: int = 10) -> set[uuid.UUID]:
    recent = select(Order.id).where(Order.retailer_id == retailer_id).order_by(Order.created_at.desc()).limit(orders)
    return set(db.scalars(select(OrderItem.product_id).where(OrderItem.order_id.in_(recent.scalar_subquery()))))
