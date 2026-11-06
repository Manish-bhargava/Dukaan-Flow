import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.constants import OrderSource, OrderStatus
from app.core.dependencies import CurrentUser, DbSession
from app.modules.orders import controller
from app.modules.orders.schemas import (
    ApproveOrderInput,
    RejectInput,
    ClarificationInput,
    CorrectOrderItemInput,
    CreateOrderInput,
    OrderOut,
    OrderPageOut,
    QuoteOut,
    StatusReasonInput,
)
from app.schemas.common import ApiResponse

# Role and retailer-access checks are enforced in the orders service for every action.
router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("/quote", response_model=ApiResponse[QuoteOut])
def quote(data: CreateOrderInput, db: DbSession, user: CurrentUser):
    """Price a cart (schemes, GST, totals, stock) without placing an order."""
    return controller.quote(db, user, data)


@router.post("", response_model=ApiResponse[OrderOut], status_code=201)
def create_order(data: CreateOrderInput, db: DbSession, user: CurrentUser):
    return controller.create(db, user, data)


@router.get("", response_model=ApiResponse[OrderPageOut])
def list_orders(
    db: DbSession,
    user: CurrentUser,
    status: Annotated[list[OrderStatus] | None, Query()] = None,
    source: OrderSource | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    created_by_me: bool = False,
    retailer_id: uuid.UUID | None = None,
):
    return controller.list_orders(db, user, status or [], source, search, page, limit, created_by_me, retailer_id)


@router.get("/{order_id}", response_model=ApiResponse[OrderOut])
def get_order(order_id: uuid.UUID, db: DbSession, user: CurrentUser):
    return controller.get(db, user, order_id)


@router.patch("/{order_id}/items/{item_id}", response_model=ApiResponse[OrderOut])
def correct_item(order_id: uuid.UUID, item_id: uuid.UUID, data: CorrectOrderItemInput, db: DbSession, user: CurrentUser):
    return controller.correct_item(db, user, order_id, item_id, data)


@router.post("/{order_id}/hold", response_model=ApiResponse[OrderOut])
def hold(order_id: uuid.UUID, data: StatusReasonInput, db: DbSession, user: CurrentUser):
    return controller.hold(db, user, order_id, data)


@router.post("/{order_id}/approve", response_model=ApiResponse[OrderOut])
def approve(order_id: uuid.UUID, data: ApproveOrderInput, db: DbSession, user: CurrentUser):
    return controller.approve(db, user, order_id, data)


@router.post("/{order_id}/clarification", response_model=ApiResponse[OrderOut])
def request_clarification(order_id: uuid.UUID, data: ClarificationInput, db: DbSession, user: CurrentUser):
    """Order Desk asks about an unclear order; it waits in CLARIFICATION_REQUIRED, unchanged."""
    return controller.request_clarification(db, user, order_id, data)


@router.post("/{order_id}/reject", response_model=ApiResponse[OrderOut])
def reject(order_id: uuid.UUID, db: DbSession, user: CurrentUser, data: RejectInput | None = None):
    return controller.reject(db, user, order_id, data)
