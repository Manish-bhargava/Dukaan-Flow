from sqlalchemy.orm import Session

from app.models import User
from app.modules.salesman import service
from app.modules.salesman.schemas import SyncStatusInput, VisitInput, VisitOut
from app.utils.responses import success_response


def sync_bundle(db: Session, user: User) -> dict:
    return success_response("Data for offline use", service.sync_bundle(db, user))


def report_sync_status(db: Session, user: User, data: SyncStatusInput) -> dict:
    service.report_sync_status(db, user, data)
    return success_response("Sync status saved", {})


def home(db: Session, user: User) -> dict:
    return success_response("Today's work", service.home(db, user))


def record_visit(db: Session, user: User, data: VisitInput) -> dict:
    visit = service.record_visit(db, user, data)
    return success_response("Visit saved", VisitOut(
        id=visit.id, retailer_id=visit.retailer_id, started_at=visit.started_at, ended_at=visit.ended_at,
        outcome=visit.outcome, order_id=visit.order_id,
    ))
