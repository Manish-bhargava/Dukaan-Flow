import uuid
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.core.constants import UserRole
from app.core.dependencies import DbSession, require_roles
from app.models import User
from app.modules.admin import controller
from app.modules.admin.schemas import (
    AssignmentInput,
    CreditUpdate,
    NamedCreate,
    NamedUpdate,
    PasswordReset,
    PriceSet,
    ProductCreate,
    ProductUpdate,
    RetailerCreate,
    RetailerUpdate,
    SchemeCreate,
    SchemeUpdate,
    StockAdjust,
    UserCreate,
    UserUpdate,
)
from app.modules.settings.service import BusinessSettings
from app.schemas.common import ApiResponse

# ADMIN only: every route requires the ADMIN role (checked against the database user), and
# every admin service checks it again.
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_roles(UserRole.ADMIN))])
Admin = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
Page = Annotated[int, Query(ge=1)]
Limit = Annotated[int, Query(ge=1, le=100)]
Search = Annotated[str | None, Query(max_length=100)]
Out = ApiResponse[Any]


# ---------------------------------------------------------------- overview and monitoring


@router.get("/dashboard", response_model=Out)
def dashboard(db: DbSession, user: Admin):
    return controller.dashboard(db, user)


@router.get("/order-desk", response_model=Out)
def order_desk(db: DbSession, user: Admin):
    """Order Desk activity: queue counts, issues, corrections, Tally export status, per-user actions."""
    return controller.order_desk(db, user)


@router.get("/audit", response_model=Out)
def audit(db: DbSession, user: Admin, source: Literal["all", "master", "orders"] = "all", entity_type: str | None = None,
          action: str | None = None, actor_id: uuid.UUID | None = None, search: Search = None,
          from_date: date | None = None, to_date: date | None = None, page: Page = 1, limit: Limit = 50):
    return controller.audit(db, user, source=source, entity_type=entity_type, action=action, actor_id=actor_id,
                            search=search, from_date=from_date, to_date=to_date, page=page, limit=limit)


@router.get("/ai-orders", response_model=Out)
def ai_orders(db: DbSession, user: Admin, state: Literal["all", "draft", "ordered", "open", "APPROVED", "REJECTED"] = "all",
              page: Page = 1, limit: Limit = 20):
    return controller.ai_orders(db, user, state, page, limit)


@router.get("/sync", response_model=Out)
def sync(db: DbSession, user: Admin):
    return controller.sync(db, user)


@router.get("/settings", response_model=Out)
def settings(db: DbSession, user: Admin):
    return controller.settings(db, user)


@router.put("/settings", response_model=Out)
def update_settings(data: BusinessSettings, db: DbSession, user: Admin):
    return controller.update_settings(db, user, data)


# ---------------------------------------------------------------- retailers and credit


@router.get("/retailers", response_model=Out)
def list_retailers(db: DbSession, user: Admin, search: Search = None,
                   status: Literal["active", "inactive", "restricted"] | None = None,
                   salesman_id: str | None = Query(default=None, pattern=r"^(none|[0-9a-fA-F-]{36})$",
                                                   description="a salesman id, or 'none' (unassigned)"),
                   sort: Literal["name", "newest", "outstanding", "last_order", "purchased"] = "name",
                   page: Page = 1, limit: Limit = 20):
    return controller.list_retailers(db, user, search=search, status=status, salesman_id=salesman_id, sort=sort,
                                     page_no=page, limit=limit)


@router.post("/retailers", response_model=Out, status_code=201)
def create_retailer(data: RetailerCreate, db: DbSession, user: Admin):
    return controller.create_retailer(db, user, data)


@router.get("/retailers/{retailer_id}", response_model=Out)
def retailer(retailer_id: uuid.UUID, db: DbSession, user: Admin):
    return controller.retailer_detail(db, retailer_id, user)


@router.patch("/retailers/{retailer_id}", response_model=Out)
def update_retailer(retailer_id: uuid.UUID, data: RetailerUpdate, db: DbSession, user: Admin):
    return controller.update_retailer(db, user, retailer_id, data)


@router.patch("/retailers/{retailer_id}/credit", response_model=Out)
def update_credit(retailer_id: uuid.UUID, data: CreditUpdate, db: DbSession, user: Admin):
    """Credit limit and pausing / allowing ordering."""
    return controller.update_credit(db, user, retailer_id, data)


@router.get("/retailers/{retailer_id}/credit-history", response_model=Out)
def credit_history(retailer_id: uuid.UUID, db: DbSession, user: Admin):
    return controller.credit_history(db, user, retailer_id)


@router.get("/retailers/{retailer_id}/prices", response_model=Out)
def retailer_prices(retailer_id: uuid.UUID, db: DbSession, user: Admin):
    return controller.retailer_prices(db, user, retailer_id)


# ---------------------------------------------------------------- salesmen, assignments, users


@router.get("/salesmen", response_model=Out)
def salesmen(db: DbSession, user: Admin):
    return controller.list_salesmen(db, user)


@router.get("/salesmen/{salesman_id}", response_model=Out)
def salesman(salesman_id: uuid.UUID, db: DbSession, user: Admin):
    return controller.salesman_detail(db, user, salesman_id)


@router.post("/assignments", response_model=Out)
def assign(data: AssignmentInput, db: DbSession, user: Admin):
    """Assign retailers to a salesman (moves them from their current one), or unassign (salesman_id null)."""
    return controller.assign(db, user, data)


@router.get("/users", response_model=Out)
def users(db: DbSession, user: Admin, role: UserRole | None = None, search: Search = None,
          status: Literal["active", "inactive"] | None = None, page: Page = 1, limit: Limit = 20):
    return controller.list_users(db, user, role=role, search=search, status=status, page_no=page, limit=limit)


@router.post("/users", response_model=Out, status_code=201)
def create_user(data: UserCreate, db: DbSession, user: Admin):
    return controller.create_user(db, user, data)


@router.get("/users/{user_id}", response_model=Out)
def user_detail(user_id: uuid.UUID, db: DbSession, user: Admin):
    return controller.user_detail(db, user, user_id)


@router.patch("/users/{user_id}", response_model=Out)
def update_user(user_id: uuid.UUID, data: UserUpdate, db: DbSession, user: Admin):
    return controller.update_user(db, user, user_id, data)


@router.post("/users/{user_id}/reset-password", response_model=Out)
def reset_password(user_id: uuid.UUID, data: PasswordReset, db: DbSession, user: Admin):
    return controller.reset_password(db, user, user_id, data)


# ---------------------------------------------------------------- catalogue, prices, schemes, stock


@router.get("/categories", response_model=Out)
def categories(db: DbSession, user: Admin):
    return controller.categories(db, user)


@router.post("/categories", response_model=Out, status_code=201)
def create_category(data: NamedCreate, db: DbSession, user: Admin):
    return controller.create_category(db, user, data)


@router.patch("/categories/{category_id}", response_model=Out)
def update_category(category_id: uuid.UUID, data: NamedUpdate, db: DbSession, user: Admin):
    return controller.update_category(db, user, category_id, data)


@router.get("/brands", response_model=Out)
def brands(db: DbSession, user: Admin):
    return controller.brands(db, user)


@router.post("/brands", response_model=Out, status_code=201)
def create_brand(data: NamedCreate, db: DbSession, user: Admin):
    return controller.create_brand(db, user, data)


@router.patch("/brands/{brand_id}", response_model=Out)
def update_brand(brand_id: uuid.UUID, data: NamedUpdate, db: DbSession, user: Admin):
    return controller.update_brand(db, user, brand_id, data)


@router.get("/products", response_model=Out)
def products(db: DbSession, user: Admin, search: Search = None, category_id: uuid.UUID | None = None,
             brand: str | None = None, status: Literal["active", "inactive"] | None = None,
             stock: Literal["low", "out"] | None = None, page: Page = 1, limit: Limit = 20):
    return controller.list_products(db, user, search=search, category_id=category_id, brand=brand, status=status,
                                    stock=stock, page_no=page, limit=limit)


@router.post("/products", response_model=Out, status_code=201)
def create_product(data: ProductCreate, db: DbSession, user: Admin):
    """Product image upload: POST /products/{id}/image (ADMIN)."""
    return controller.create_product(db, user, data)


@router.get("/products/{product_id}", response_model=Out)
def product(product_id: uuid.UUID, db: DbSession, user: Admin):
    return controller.product_detail(db, user, product_id)


@router.patch("/products/{product_id}", response_model=Out)
def update_product(product_id: uuid.UUID, data: ProductUpdate, db: DbSession, user: Admin):
    return controller.update_product(db, user, product_id, data)


@router.put("/prices", response_model=Out)
def set_price(data: PriceSet, db: DbSession, user: Admin):
    """Set the default price (retailer_id null) or a retailer's own price, from now on."""
    return controller.set_price(db, user, data)


@router.delete("/prices", response_model=Out)
def remove_price(db: DbSession, user: Admin, product_id: uuid.UUID, retailer_id: uuid.UUID):
    """End a retailer's own price (the default price applies again)."""
    return controller.remove_price(db, user, product_id, retailer_id)


@router.get("/schemes", response_model=Out)
def schemes(db: DbSession, user: Admin, search: Search = None, product_id: uuid.UUID | None = None,
            state: Literal["all", "active", "upcoming", "expired", "inactive"] = "all", page: Page = 1, limit: Limit = 20):
    return controller.list_schemes(db, user, search=search, product_id=product_id, state=state, page_no=page, limit=limit)


@router.post("/schemes", response_model=Out, status_code=201)
def create_schemes(data: SchemeCreate, db: DbSession, user: Admin):
    return controller.create_schemes(db, user, data)


@router.patch("/schemes/{scheme_id}", response_model=Out)
def update_scheme(scheme_id: uuid.UUID, data: SchemeUpdate, db: DbSession, user: Admin):
    return controller.update_scheme(db, user, scheme_id, data)


@router.get("/stock", response_model=Out)
def stock(db: DbSession, user: Admin, search: Search = None, category_id: uuid.UUID | None = None,
          stock: Literal["low", "out"] | None = None, page: Page = 1, limit: Limit = 20):
    return controller.list_stock(db, user, search=search, category_id=category_id, stock=stock, page_no=page, limit=limit)


@router.post("/stock/{product_id}/adjust", response_model=Out)
def adjust_stock(product_id: uuid.UUID, data: StockAdjust, db: DbSession, user: Admin):
    return controller.adjust_stock(db, user, product_id, data)


@router.get("/stock/{product_id}/history", response_model=Out)
def stock_history(product_id: uuid.UUID, db: DbSession, user: Admin):
    return controller.stock_history(db, user, product_id)


# ---------------------------------------------------------------- reports


@router.get("/reports", response_model=Out)
def report_list():
    return controller.report_list()


@router.get("/reports/{name}", response_model=Out)
def report(name: str, db: DbSession, user: Admin, from_date: date | None = None, to_date: date | None = None):
    return controller.report(db, user, name, from_date, to_date)


@router.get("/reports/{name}/csv", response_class=Response)
def report_csv(name: str, db: DbSession, user: Admin, from_date: date | None = None, to_date: date | None = None):
    content, filename = controller.report_csv(db, user, name, from_date, to_date)
    return Response(content="﻿" + content, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
