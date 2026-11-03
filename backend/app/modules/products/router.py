import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.constants import UserRole
from app.core.dependencies import DbSession, require_roles
from app.models import User
from app.modules.products import controller
from app.modules.products.schemas import CategoryOut, ProductPageOut
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/products", tags=["products"])

# V1: the catalogue with dealer prices is the retailer's own view.
Retailer = Annotated[User, Depends(require_roles(UserRole.RETAILER))]


@router.get("/categories", response_model=ApiResponse[list[CategoryOut]])
def list_categories(db: DbSession, user: Retailer):
    return controller.list_categories(db)


@router.get("", response_model=ApiResponse[ProductPageOut])
def list_products(
    db: DbSession,
    user: Retailer,
    search: Annotated[str | None, Query(max_length=100)] = None,
    category_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    return controller.list_products(db, user, search, category_id, page, limit)
