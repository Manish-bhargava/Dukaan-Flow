import uuid

from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.core.dependencies import CurrentUser, DbSession
from app.modules.ai_orders import controller
from app.modules.ai_orders.schemas import ConfirmExtractionInput, DraftSummaryOut, ExtractionOut, ExtractOrderInput
from app.modules.orders.schemas import OrderOut
from app.schemas.common import ApiResponse

# Only RETAILER (own shop) and SALESMAN (assigned shops) may capture orders; checked in the service.
router = APIRouter(prefix="/ai-orders", tags=["ai orders"])


@router.get("", response_model=ApiResponse[list[DraftSummaryOut]])
def list_drafts(db: DbSession, user: CurrentUser, retailer_id: uuid.UUID | None = None):
    """The retailer's AI drafts that have not been placed as orders yet (newest 20)."""
    return controller.list_drafts(db, user, retailer_id)


@router.post("/extract", response_model=ApiResponse[ExtractionOut])
def extract(data: ExtractOrderInput, db: DbSession, user: CurrentUser):
    """Read a free-text order into a draft. Never creates an order."""
    return controller.extract(db, user, data)


@router.post("/extract-media", response_model=ApiResponse[ExtractionOut])
async def extract_media(
    db: DbSession, user: CurrentUser, kind: Annotated[Literal["image", "voice"], Form()],
    file: Annotated[UploadFile, File()], retailer_id: Annotated[uuid.UUID | None, Form()] = None,
):
    """Read a photo of an order list or a voice note into a draft. Never creates an order."""
    content = await file.read(10 * 1024 * 1024 + 1)
    return await run_in_threadpool(controller.extract_media, db, user, kind=kind, content=content,
                                   content_type=file.content_type, filename=file.filename, retailer_id=retailer_id)


@router.get("/{extraction_id}", response_model=ApiResponse[ExtractionOut])
def get_extraction(extraction_id: uuid.UUID, db: DbSession, user: CurrentUser):
    return controller.get(db, user, extraction_id)


@router.post("/{extraction_id}/confirm", response_model=ApiResponse[OrderOut], status_code=201)
def confirm(extraction_id: uuid.UUID, data: ConfirmExtractionInput, db: DbSession, user: CurrentUser):
    """Place the reviewed draft as an order (source AI); priced and validated like any order."""
    return controller.confirm(db, user, extraction_id, data)
