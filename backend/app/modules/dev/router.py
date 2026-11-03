"""Temporary development-only endpoints for verifying the database and seed data.

Mounted only when ENVIRONMENT=development (see app/main.py). No authentication:
never enable in any shared or production environment.
"""

import uuid

from fastapi import APIRouter

from app.core.constants import OrderStatus

from app.core.dependencies import DbSession
from app.modules.dev import controller
from app.modules.dev.schemas import (
    CreditDetailOut,
    DbStatusOut,
    ExtractionOut,
    IntegrityOut,
    InventoryOut,
    OrderDetailOut,
    OrderSummaryOut,
    UserOut,
    ProductOut,
    RetailerOut,
    RetailerProductsOut,
    SeedSummaryOut,
)
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/dev", tags=["dev (development only)"])


@router.get("/db-status", response_model=ApiResponse[DbStatusOut])
def db_status(db: DbSession):
    return controller.db_status(db)


@router.get("/seed-summary", response_model=ApiResponse[SeedSummaryOut])
def seed_summary(db: DbSession):
    return controller.seed_summary(db)


@router.get("/products", response_model=ApiResponse[list[ProductOut]])
def products(db: DbSession):
    return controller.products(db)


@router.get("/retailers", response_model=ApiResponse[list[RetailerOut]])
def retailers(db: DbSession):
    return controller.retailers(db)


@router.get(
    "/retailers/{retailer_id}/products", response_model=ApiResponse[RetailerProductsOut]
)
def retailer_products(retailer_id: uuid.UUID, db: DbSession):
    return controller.retailer_products(db, retailer_id)


@router.get("/users", response_model=ApiResponse[list[UserOut]])
def users(db: DbSession):
    return controller.users(db)


@router.get("/orders", response_model=ApiResponse[list[OrderSummaryOut]])
def orders(db: DbSession, status: OrderStatus | None = None):
    return controller.orders(db, status)


@router.get("/orders/{order_ref}", response_model=ApiResponse[OrderDetailOut])
def order_detail(order_ref: str, db: DbSession):
    """order_ref is the order UUID or its number, e.g. DF-DEMO-0002."""
    return controller.order_detail(db, order_ref)


@router.get("/ai-extractions", response_model=ApiResponse[list[ExtractionOut]])
def ai_extractions(db: DbSession):
    return controller.ai_extractions(db)


@router.get("/inventory", response_model=ApiResponse[list[InventoryOut]])
def inventory(db: DbSession):
    return controller.inventory(db)


@router.get("/retailers/{retailer_id}/credit", response_model=ApiResponse[CreditDetailOut])
def retailer_credit(retailer_id: uuid.UUID, db: DbSession):
    return controller.retailer_credit(db, retailer_id)


@router.get("/integrity", response_model=ApiResponse[IntegrityOut])
def integrity(db: DbSession):
    return controller.integrity(db)
