from datetime import date, datetime

from fastapi import APIRouter
from fastapi.responses import Response

from app.core.dependencies import CurrentUser, DbSession
from app.modules.exports import service
from app.modules.exports.schemas import TallyExportInput
from app.modules.exports.tally import IST

router = APIRouter(prefix="/exports", tags=["exports"])


def _csv(content: str, name: str, **headers: str) -> Response:
    return Response(
        content="\ufeff" + content,  # BOM so Excel opens ₹/Hindi text as UTF-8
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"', **headers},
    )


@router.post("/tally", response_class=Response)
def export_tally(data: TallyExportInput, db: DbSession, user: CurrentUser):
    """Export confirmed orders to Tally CSV and mark them exported (ORDER_DESK / ADMIN).
    Already exported orders are skipped unless include_exported; 409 NOTHING_TO_EXPORT if none."""
    content, count = service.export_to_tally(
        db, user, from_date=data.from_date, to_date=data.to_date, order_ids=data.order_ids,
        include_exported=data.include_exported,
    )
    name = f"dukaanflow-tally-{datetime.now(IST):%Y%m%d-%H%M}.csv"
    return _csv(content, name, **{"X-Exported-Count": str(count)})


@router.get("/tally/orders.csv", response_class=Response)
def tally_orders(db: DbSession, user: CurrentUser, from_date: date | None = None, to_date: date | None = None):
    """Read-only Tally CSV of confirmed orders (ORDER_DESK / ADMIN); does not mark them exported.
    Dates filter by confirmation date (IST)."""
    content = service.tally_orders_csv(db, user, from_date, to_date)
    name = f"dukaanflow-orders-{from_date or 'all'}-to-{to_date or 'latest'}.csv"
    return _csv(content, name)
