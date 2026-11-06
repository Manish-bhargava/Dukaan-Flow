import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.constants import OrderSource, OrderStatus
from app.core.dependencies import CurrentUser, DbSession
from app.modules.order_desk import controller
from app.modules.order_desk.schemas import (
    DeskOrderPageOut,
    DispatchOut,
    OrderReviewOut,
    OverviewOut,
    PersonOut,
)
from app.schemas.common import ApiResponse

# ORDER_DESK / ADMIN only: enforced in the order_desk service. Actions on an order (confirm,
# reject, clarification, correction) are the /orders endpoints.
router = APIRouter(prefix="/order-desk", tags=["order desk"])


@router.get("/summary", response_model=ApiResponse[dict[str, int]])
def summary(db: DbSession, user: CurrentUser):
    """Order counts per status."""
    return controller.summary(db, user)


@router.get("/overview", response_model=ApiResponse[OverviewOut])
def overview(db: DbSession, user: CurrentUser):
    return controller.overview(db, user)


@router.get("/orders", response_model=ApiResponse[DeskOrderPageOut])
def list_orders(
    db: DbSession,
    user: CurrentUser,
    view: str = "incoming",
    status: Annotated[list[OrderStatus] | None, Query()] = None,
    source: OrderSource | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    salesman_id: uuid.UUID | None = None,
    retailer_id: uuid.UUID | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    exported: bool | None = None,
    sort: str = "newest",
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    """One Order Desk section (incoming, clarification, confirmed, rejected, all) with
    warnings, salesman and last action per order."""
    return controller.list_orders(
        db, user, view=view, statuses=status or [], source=source, search=search, salesman_id=salesman_id,
        from_date=from_date, to_date=to_date, exported=exported, sort=sort, page=page, limit=limit,
        retailer_id=retailer_id,
    )


@router.get("/orders/{order_id}", response_model=ApiResponse[OrderReviewOut])
def review(order_id: uuid.UUID, db: DbSession, user: CurrentUser):
    """Order with retailer credit, stock per line, warnings, AI lines and full history."""
    return controller.review(db, user, order_id)


@router.get("/salesmen", response_model=ApiResponse[list[PersonOut]])
def salesmen(db: DbSession, user: CurrentUser):
    return controller.salesmen(db, user)


@router.get("/dispatch", response_model=ApiResponse[DispatchOut])
def dispatch(db: DbSession, user: CurrentUser, from_date: date | None = None, to_date: date | None = None,
             salesman_id: uuid.UUID | None = None):
    """Loading list: consolidated quantities of confirmed orders (default: confirmed today)."""
    return controller.dispatch(db, user, from_date, to_date, salesman_id)
