import uuid

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AiExtraction,
    AiExtractionItem,
    Category,
    CreditAccount,
    CreditLedger,
    Inventory,
    Order,
    OrderCorrection,
    OrderItem,
    OtpVerification,
    Product,
    Retailer,
    RetailerAlias,
    RetailerPrice,
    Scheme,
    StockMovement,
    User,
)


def get_server_info(db: Session) -> tuple[str, str]:
    row = db.execute(text("SELECT current_database(), current_setting('server_version')")).one()
    return row[0], row[1]


def get_migration_revision(db: Session) -> str | None:
    return db.execute(text("SELECT version_num FROM alembic_version")).scalar()


def count_rows(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def count_users_by_role(db: Session) -> dict[str, int]:
    rows = db.execute(select(User.role, func.count()).group_by(User.role)).all()
    return {role: count for role, count in rows}


def count_seed_tables(db: Session) -> dict[str, int]:
    tables = {
        "users": User,
        "retailers": Retailer,
        "categories": Category,
        "products": Product,
        "retailer_prices": RetailerPrice,
        "schemes": Scheme,
        "inventory_records": Inventory,
        "retailer_aliases": RetailerAlias,
        "credit_accounts": CreditAccount,
        "credit_ledger": CreditLedger,
        "stock_movements": StockMovement,
        "orders": Order,
        "order_items": OrderItem,
        "order_corrections": OrderCorrection,
        "ai_extractions": AiExtraction,
        "ai_extraction_items": AiExtractionItem,
        "otp_verifications": OtpVerification,
    }
    return {name: count_rows(db, model) for name, model in tables.items()}


def list_products(db: Session, active_only: bool = False) -> list[Product]:
    statement = (
        select(Product)
        .options(selectinload(Product.category), selectinload(Product.inventory))
        .order_by(Product.sku)
    )
    if active_only:
        statement = statement.where(Product.is_active.is_(True))
    return list(db.scalars(statement))


def list_retailers(db: Session) -> list[Retailer]:
    statement = (
        select(Retailer)
        .options(selectinload(Retailer.assigned_salesman), selectinload(Retailer.credit_account))
        .order_by(Retailer.shop_name)
    )
    return list(db.scalars(statement))


def get_retailer(db: Session, retailer_id: uuid.UUID) -> Retailer | None:
    return db.get(Retailer, retailer_id)


def count_orders_by_status(db: Session) -> dict[str, int]:
    return {status: n for status, n in db.execute(select(Order.status, func.count()).group_by(Order.status))}


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.role, User.name)))


def list_orders(db: Session, status: str | None) -> list[Order]:
    statement = (
        select(Order)
        .options(selectinload(Order.retailer), selectinload(Order.items))
        .order_by(Order.created_at.desc(), Order.order_number)
    )
    if status:
        statement = statement.where(Order.status == status)
    return list(db.scalars(statement))


def find_order(db: Session, order_ref: str) -> Order | None:
    """Look up by UUID or by order number (e.g. DF-DEMO-0002)."""
    statement = select(Order).options(selectinload(Order.retailer), selectinload(Order.items))
    try:
        return db.scalar(statement.where(Order.id == uuid.UUID(order_ref)))
    except ValueError:
        return db.scalar(statement.where(Order.order_number == order_ref))


def list_corrections(db: Session, order_item_ids: list[uuid.UUID]) -> list[OrderCorrection]:
    statement = (
        select(OrderCorrection)
        .where(OrderCorrection.order_item_id.in_(order_item_ids))
        .order_by(OrderCorrection.created_at)
    )
    return list(db.scalars(statement))


def list_stock_movements(
    db: Session, order_id: uuid.UUID | None = None, product_id: uuid.UUID | None = None
) -> list[StockMovement]:
    statement = select(StockMovement).order_by(StockMovement.created_at)
    if order_id is not None:
        statement = statement.where(StockMovement.order_id == order_id)
    if product_id is not None:
        statement = statement.where(StockMovement.product_id == product_id)
    return list(db.scalars(statement))


def list_ledger_entries(
    db: Session, order_id: uuid.UUID | None = None, retailer_id: uuid.UUID | None = None
) -> list[CreditLedger]:
    statement = select(CreditLedger).order_by(CreditLedger.created_at)
    if order_id is not None:
        statement = statement.where(CreditLedger.order_id == order_id)
    if retailer_id is not None:
        statement = statement.where(CreditLedger.retailer_id == retailer_id)
    return list(db.scalars(statement))


def list_extractions(db: Session) -> list[AiExtraction]:
    statement = (
        select(AiExtraction).options(selectinload(AiExtraction.items)).order_by(AiExtraction.created_at)
    )
    return list(db.scalars(statement))


def order_numbers_by_extraction(db: Session) -> dict[uuid.UUID, str]:
    statement = select(Order.ai_extraction_id, Order.order_number).where(Order.ai_extraction_id.is_not(None))
    return {extraction_id: number for extraction_id, number in db.execute(statement)}


def list_inventory(db: Session) -> list[tuple[Inventory, Product]]:
    statement = select(Inventory, Product).join(Product, Product.id == Inventory.product_id).order_by(Product.sku)
    return [(inventory, product) for inventory, product in db.execute(statement)]


def get_credit_account(db: Session, retailer_id: uuid.UUID) -> CreditAccount | None:
    return db.scalar(select(CreditAccount).where(CreditAccount.retailer_id == retailer_id))


# Each integrity query returns the identifiers of the records that break the rule.
INTEGRITY_QUERIES = {
    "credit_ledger_matches_outstanding": """
        SELECT r.shop_name FROM credit_accounts a JOIN retailers r ON r.id = a.retailer_id
        LEFT JOIN credit_ledger l ON l.retailer_id = a.retailer_id
        GROUP BY r.shop_name, a.current_outstanding
        HAVING COALESCE(SUM(l.amount), 0) <> a.current_outstanding""",
    "stock_movements_match_inventory": """
        SELECT p.sku FROM inventory i JOIN products p ON p.id = i.product_id
        LEFT JOIN stock_movements m ON m.product_id = i.product_id
        GROUP BY p.sku, i.stock_cases HAVING COALESCE(SUM(m.quantity), 0) <> i.stock_cases""",
    "order_totals_match_items": """
        SELECT o.order_number FROM orders o JOIN order_items i ON i.order_id = o.id GROUP BY o.id
        HAVING SUM(i.line_total) <> o.grand_total OR SUM(i.taxable_amount) <> o.taxable_amount
            OR SUM(i.gst_amount) <> o.gst_amount OR SUM(i.discount_amount) <> o.discount_total
            OR o.subtotal - o.discount_total <> o.taxable_amount""",
    "approved_orders_have_stock_and_credit_records": """
        SELECT o.order_number FROM orders o WHERE o.status = 'APPROVED' AND (
            NOT EXISTS (SELECT 1 FROM stock_movements m WHERE m.order_id = o.id)
            OR NOT EXISTS (SELECT 1 FROM credit_ledger l WHERE l.order_id = o.id
                           AND l.transaction_type = 'ORDER_DEBIT')
            OR o.approved_by IS NULL OR o.approved_at IS NULL)""",
    "other_orders_have_no_stock_or_credit_records": """
        SELECT o.order_number FROM orders o WHERE o.status <> 'APPROVED' AND (
            EXISTS (SELECT 1 FROM stock_movements m WHERE m.order_id = o.id)
            OR EXISTS (SELECT 1 FROM credit_ledger l WHERE l.order_id = o.id))""",
    "rejected_orders_have_reason": """
        SELECT order_number FROM orders
        WHERE status = 'REJECTED' AND COALESCE(TRIM(rejection_reason), '') = ''""",
    "every_retailer_has_credit_account": """
        SELECT r.shop_name FROM retailers r
        WHERE NOT EXISTS (SELECT 1 FROM credit_accounts a WHERE a.retailer_id = r.id)""",
    "every_product_has_inventory": """
        SELECT p.sku FROM products p WHERE NOT EXISTS (SELECT 1 FROM inventory i WHERE i.product_id = p.id)""",
    "confirmed_extractions_have_an_order": """
        SELECT e.id::text FROM ai_extractions e WHERE e.extraction_status = 'CONFIRMED'
        AND NOT EXISTS (SELECT 1 FROM orders o WHERE o.ai_extraction_id = e.id)""",
}


def run_integrity_queries(db: Session) -> dict[str, list[str]]:
    return {name: [str(row[0]) for row in db.execute(text(sql))] for name, sql in INTEGRITY_QUERIES.items()}
