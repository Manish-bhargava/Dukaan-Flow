import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AiExtraction,
    AiExtractionItem,
    Category,
    Order,
    OrderCorrection,
    OrderItem,
    Product,
    RetailerAlias,
)
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


def list_open_extractions(db: Session, retailer_id: uuid.UUID, statuses: list[str], limit: int) -> list[AiExtraction]:
    statement = (
        select(AiExtraction)
        .where(AiExtraction.retailer_id == retailer_id, AiExtraction.extraction_status.in_(statuses))
        .options(selectinload(AiExtraction.items))
        .order_by(AiExtraction.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(statement))


def get_phrase_history(db: Session, retailer_id: uuid.UUID, since, limit: int = 300) -> list[tuple]:
    """This retailer's earlier AI lines that became order lines (not rejected), newest first:
    (original_text, quantity, product the line is now, corrected by the Order Desk?, when).
    The order line's current product includes any Order Desk correction, so it is what the
    retailer meant."""
    corrected = (
        select(OrderCorrection.order_item_id)
        .where(OrderCorrection.old_product_id.is_distinct_from(OrderCorrection.new_product_id))
        .scalar_subquery()
    )
    statement = (
        select(AiExtractionItem.original_text, AiExtractionItem.quantity, OrderItem.product_id,
               OrderItem.id.in_(corrected), AiExtractionItem.created_at)
        .join(OrderItem, OrderItem.id == AiExtractionItem.order_item_id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.retailer_id == retailer_id, Order.status != "REJECTED", AiExtractionItem.created_at >= since)
        .order_by(AiExtractionItem.created_at.desc())
        .limit(limit)
    )
    return list(db.execute(statement).tuples())


def get_product_frequency(db: Session, retailer_id: uuid.UUID, since) -> dict[uuid.UUID, int]:
    """How many of this retailer's order lines (not rejected) since `since` had each product."""
    statement = (
        select(OrderItem.product_id, func.count())
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.retailer_id == retailer_id, Order.status != "REJECTED", Order.created_at >= since)
        .group_by(OrderItem.product_id)
    )
    return dict(db.execute(statement).tuples().all())


def extraction_item_for_order_item(db: Session, order_item_id: uuid.UUID) -> AiExtractionItem | None:
    return db.scalar(select(AiExtractionItem).where(AiExtractionItem.order_item_id == order_item_id))
