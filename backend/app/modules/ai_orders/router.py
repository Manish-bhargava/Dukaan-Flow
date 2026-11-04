import uuid

from fastapi import APIRouter

from app.core.dependencies import CurrentUser, DbSession
from app.modules.ai_orders import controller
from app.modules.ai_orders.schemas import ConfirmExtractionInput, ExtractionOut, ExtractOrderInput
from app.modules.orders.schemas import OrderOut
from app.schemas.common import ApiResponse

# Only RETAILER (own shop) and SALESMAN (assigned shops) may capture orders; checked in the service.
router = APIRouter(prefix="/ai-orders", tags=["ai orders"])


@router.post("/extract", response_model=ApiResponse[ExtractionOut])
def extract(data: ExtractOrderInput, db: DbSession, user: CurrentUser):
    """Read a free-text order into a draft. Never creates an order."""
    return controller.extract(db, user, data)


@router.get("/{extraction_id}", response_model=ApiResponse[ExtractionOut])
def get_extraction(extraction_id: uuid.UUID, db: DbSession, user: CurrentUser):
    return controller.get(db, user, extraction_id)


@router.post("/{extraction_id}/confirm", response_model=ApiResponse[OrderOut], status_code=201)
def confirm(extraction_id: uuid.UUID, data: ConfirmExtractionInput, db: DbSession, user: CurrentUser):
    """Place the reviewed draft as an order (source AI); priced and validated like any order."""
    return controller.confirm(db, user, extraction_id, data)
