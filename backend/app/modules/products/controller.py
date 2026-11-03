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
    db: Session, user: User, search: str | None, category_id: uuid.UUID | None, page: int, limit: int
) -> dict:
    result = service.list_catalogue(db, user, search, category_id, page, limit)
    return success_response("Products fetched successfully", result)
