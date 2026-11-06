from fastapi import APIRouter

from app.core.dependencies import CurrentUser, DbSession
from app.modules.salesman import controller
from app.modules.salesman.schemas import SalesmanHomeOut, SyncBundleOut, SyncStatusInput, VisitInput, VisitOut
from app.schemas.common import ApiResponse

# SALESMAN only; every retailer is checked against the salesman's assignments in the service.
router = APIRouter(prefix="/salesman", tags=["salesman"])


@router.get("/sync-bundle", response_model=ApiResponse[SyncBundleOut])
def sync_bundle(db: DbSession, user: CurrentUser):
    """Everything the salesman app keeps for offline use: assigned retailers (details,
    credit, recent orders), products with stock and schemes, and each retailer's prices."""
    return controller.sync_bundle(db, user)


@router.post("/sync-status", response_model=ApiResponse[dict])
def report_sync_status(data: SyncStatusInput, db: DbSession, user: CurrentUser):
    """The phone's outbox after a sync run (pending / failed orders, pending visits), for the Admin."""
    return controller.report_sync_status(db, user, data)


@router.get("/home", response_model=ApiResponse[SalesmanHomeOut])
def home(db: DbSession, user: CurrentUser):
    """Today's assigned retailers, visits and orders, from the server."""
    return controller.home(db, user)


@router.post("/visits", response_model=ApiResponse[VisitOut])
def record_visit(data: VisitInput, db: DbSession, user: CurrentUser):
    """Create or update a shop visit (same id = same visit)."""
    return controller.record_visit(db, user, data)
