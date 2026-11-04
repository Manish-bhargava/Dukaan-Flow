import uuid
from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.core.dependencies import CurrentUser, DbSession
from app.modules.products import controller
from app.modules.products.images import MAX_BYTES
from app.modules.products.schemas import CategoryOut, ProductImageOut, ProductOut, ProductPageOut
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/products", tags=["products"])

@router.get("/categories", response_model=ApiResponse[list[CategoryOut]])
def list_categories(db: DbSession, user: CurrentUser):
    return controller.list_categories(db)


@router.get("", response_model=ApiResponse[ProductPageOut])
def list_products(
    db: DbSession,
    user: CurrentUser,
    search: Annotated[str | None, Query(max_length=100)] = None,
    category_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    retailer_id: uuid.UUID | None = None,
    has_scheme: bool = False,
):
    """A retailer's catalogue with their prices. Retailers: their own; staff: pass retailer_id.
    `has_scheme=true` lists only products with a currently active scheme (offers)."""
    return controller.list_products(db, user, search, category_id, page, limit, retailer_id, has_scheme)


@router.get("/{product_id}", response_model=ApiResponse[ProductOut])
def get_product(product_id: uuid.UUID, db: DbSession, user: CurrentUser, retailer_id: uuid.UUID | None = None):
    """One product with the retailer's price, stock and active schemes (same access rules as the list)."""
    return controller.get_product(db, user, product_id, retailer_id)


@router.post("/{product_id}/image", response_model=ApiResponse[ProductImageOut])
async def upload_image(product_id: uuid.UUID, db: DbSession, user: CurrentUser, file: UploadFile = File(...)):
    """ADMIN only: upload or replace the product image (JPEG/PNG/WebP, max 5 MB) on Cloudinary."""
    content = await file.read(MAX_BYTES + 1)  # read at most one byte over the limit
    return await run_in_threadpool(controller.upload_image, db, user, product_id, content, file.content_type)
