import uuid

from sqlalchemy.orm import Session

from app.models import User
from app.modules.products import service
from app.modules.products.schemas import CategoryOut
from app.utils.responses import success_response


def list_categories(db: Session) -> dict:
    categories = [CategoryOut(id=c.id, name=c.name) for c in service.list_categories(db)]
    return success_response("Categories fetched successfully", categories)


def list_products(
    db: Session, user: User, search: str | None, category_id: uuid.UUID | None, page: int, limit: int,
    retailer_id: uuid.UUID | None = None,
    has_scheme: bool = False,
) -> dict:
    result = service.list_catalogue(db, user, search, category_id, page, limit, retailer_id, has_scheme)
    return success_response("Products fetched successfully", result)


def get_product(db: Session, user: User, product_id: uuid.UUID, retailer_id: uuid.UUID | None) -> dict:
    return success_response("Product fetched successfully", service.get_catalogue_product(db, user, product_id, retailer_id))


def upload_image(db: Session, user: User, product_id: uuid.UUID, content: bytes, content_type: str | None) -> dict:
    result = service.upload_product_image(db, user, product_id, content, content_type)
    return success_response("Product image uploaded", result)
