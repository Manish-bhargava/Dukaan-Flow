from datetime import date

from fastapi import APIRouter
from fastapi.responses import Response

from app.core.dependencies import CurrentUser, DbSession
from app.modules.exports import service

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/tally/orders.csv", response_class=Response)
def tally_orders(db: DbSession, user: CurrentUser, from_date: date | None = None, to_date: date | None = None):
    """Confirmed orders as Tally CSV (ORDER_DESK / ADMIN). Dates filter by confirmation date (IST)."""
    content = service.tally_orders_csv(db, user, from_date, to_date)
    name = f"dukaanflow-orders-{from_date or 'all'}-to-{to_date or 'latest'}.csv"
    return Response(
        content="﻿" + content,  # BOM so Excel opens ₹/Hindi text as UTF-8
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
