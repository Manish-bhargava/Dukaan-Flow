import uuid
from collections.abc import Iterable
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Inventory, StockMovement


def get_stock(db: Session, product_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
    """Current stock in cases (no lock; for validation before an order is submitted)."""
    statement = select(Inventory.product_id, Inventory.stock_cases).where(
        Inventory.product_id.in_(list(product_ids))
    )
    return {product_id: stock for product_id, stock in db.execute(statement)}


def lock_inventory(db: Session, product_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Inventory]:
    """SELECT ... FOR UPDATE on the inventory rows, always in product_id order so that
    concurrent approvals lock rows in the same sequence and cannot deadlock."""
    statement = (
        select(Inventory)
        .where(Inventory.product_id.in_(sorted(set(product_ids))))
        .order_by(Inventory.product_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return {row.product_id: row for row in db.scalars(statement)}


def add_movement(db: Session, movement: StockMovement) -> None:
    db.add(movement)
