import uuid

from sqlalchemy.orm import Session

from app.modules.dev import service
from app.utils.responses import success_response


def db_status(db: Session) -> dict:
    return success_response("Database connection is healthy", service.get_db_status(db))


def seed_summary(db: Session) -> dict:
    return success_response("Seed summary fetched successfully", service.get_seed_summary(db))


def products(db: Session) -> dict:
    return success_response("Products fetched successfully", service.list_products(db))


def retailers(db: Session) -> dict:
    return success_response("Retailers fetched successfully", service.list_retailers(db))


def retailer_products(db: Session, retailer_id: uuid.UUID) -> dict:
    return success_response(
        "Retailer products fetched successfully", service.get_retailer_products(db, retailer_id)
    )


def users(db: Session) -> dict:
    return success_response("Users fetched successfully", service.list_users(db))


def orders(db: Session, status: str | None) -> dict:
    return success_response("Orders fetched successfully", service.list_orders(db, status))


def order_detail(db: Session, order_ref: str) -> dict:
    return success_response("Order fetched successfully", service.get_order_detail(db, order_ref))


def ai_extractions(db: Session) -> dict:
    return success_response("AI extractions fetched successfully", service.list_extractions(db))


def inventory(db: Session) -> dict:
    return success_response("Inventory fetched successfully", service.list_inventory(db))


def retailer_credit(db: Session, retailer_id: uuid.UUID) -> dict:
    return success_response("Credit details fetched successfully", service.get_retailer_credit(db, retailer_id))


def integrity(db: Session) -> dict:
    result = service.check_integrity(db)
    message = "All integrity checks passed" if result.all_passed else "Some integrity checks failed"
    return success_response(message, result)
