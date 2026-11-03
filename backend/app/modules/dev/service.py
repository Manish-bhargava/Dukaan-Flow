import time
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.constants import ErrorCode
from app.exceptions.base import AppException
from app.models import Order, Product, Retailer
from app.modules.dev import repository
from app.modules.pricing import repository as pricing_repository
from app.modules.dev.schemas import (
    CorrectionOut,
    CreditDetailOut,
    CreditOut,
    ExtractionItemOut,
    ExtractionOut,
    IntegrityCheckOut,
    IntegrityOut,
    InventoryOut,
    LedgerEntryOut,
    OrderDetailOut,
    OrderItemOut,
    OrderSummaryOut,
    StockMovementOut,
    UserOut,
    DbStatusOut,
    ProductOut,
    RetailerOut,
    RetailerPriceOut,
    RetailerProductOut,
    RetailerProductsOut,
    RetailerRef,
    SalesmanOut,
    SchemeOut,
    SeedSummaryOut,
)


def get_db_status(db: Session) -> DbStatusOut:
    started = time.perf_counter()
    database, server_version = repository.get_server_info(db)
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    return DbStatusOut(
        status="connected",
        database=database,
        server_version=server_version,
        migration_revision=repository.get_migration_revision(db),
        latency_ms=latency_ms,
    )


def get_seed_summary(db: Session) -> SeedSummaryOut:
    return SeedSummaryOut(
        **repository.count_seed_tables(db),
        users_by_role=repository.count_users_by_role(db),
        orders_by_status=repository.count_orders_by_status(db),
    )


def _product_fields(product: Product) -> dict:
    return {
        "id": product.id,
        "sku": product.sku,
        "name": product.name,
        "brand": product.brand,
        "category": product.category.name,
        "pack_size": product.pack_size,
        "units_per_case": product.units_per_case,
        "base_unit": product.base_unit,
        "order_unit": product.order_unit,
        "gst_rate": product.gst_rate,
        "is_active": product.is_active,
        "stock_cases": product.inventory.stock_cases if product.inventory else None,
    }


def list_products(db: Session) -> list[ProductOut]:
    return [ProductOut(**_product_fields(p)) for p in repository.list_products(db)]


def _retailer_out(retailer: Retailer) -> RetailerOut:
    salesman = retailer.assigned_salesman
    account = retailer.credit_account
    return RetailerOut(
        id=retailer.id,
        shop_name=retailer.shop_name,
        owner_name=retailer.owner_name,
        phone=retailer.phone,
        address=retailer.address,
        city=retailer.city,
        gstin=retailer.gstin,
        is_active=retailer.is_active,
        assigned_salesman=(
            SalesmanOut(id=salesman.id, name=salesman.name, phone=salesman.phone)
            if salesman
            else None
        ),
        credit=(
            CreditOut(
                credit_limit=account.credit_limit,
                current_outstanding=account.current_outstanding,
                available_credit=account.credit_limit - account.current_outstanding,
            )
            if account
            else None
        ),
    )


def list_retailers(db: Session) -> list[RetailerOut]:
    return [_retailer_out(r) for r in repository.list_retailers(db)]


def get_retailer_products(db: Session, retailer_id: uuid.UUID) -> RetailerProductsOut:
    retailer = repository.get_retailer(db, retailer_id)
    if retailer is None:
        raise AppException(
            "Retailer not found",
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            details={"retailer_id": str(retailer_id)},
        )

    now = datetime.now(UTC)
    prices = pricing_repository.get_effective_prices(db, retailer_id, now)
    schemes = pricing_repository.get_active_schemes(db, now)

    products = []
    for product in repository.list_products(db, active_only=True):
        price = prices.get(product.id)
        products.append(
            RetailerProductOut(
                **_product_fields(product),
                price=(
                    RetailerPriceOut(
                        dealer_price=price.dealer_price,
                        price_basis=price.price_basis,
                        tax_inclusive=price.tax_inclusive,
                        effective_from=price.effective_from,
                        effective_to=price.effective_to,
                    )
                    if price
                    else None
                ),
                schemes=[
                    SchemeOut(
                        id=s.id,
                        scheme_type=s.scheme_type,
                        min_quantity=s.min_quantity,
                        free_quantity=s.free_quantity,
                        discount_percentage=s.discount_percentage,
                        starts_at=s.starts_at,
                        ends_at=s.ends_at,
                    )
                    for s in schemes.get(product.id, [])
                ],
            )
        )

    return RetailerProductsOut(
        retailer=RetailerRef(id=retailer.id, shop_name=retailer.shop_name), products=products
    )


def list_users(db: Session) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in repository.list_users(db)]


def _order_summary_fields(order: Order) -> dict:
    return {
        "id": order.id,
        "order_number": order.order_number,
        "retailer_id": order.retailer_id,
        "shop_name": order.retailer.shop_name,
        "source": order.source,
        "status": order.status,
        "item_count": len(order.items),
        "subtotal": order.subtotal,
        "discount_total": order.discount_total,
        "taxable_amount": order.taxable_amount,
        "gst_amount": order.gst_amount,
        "grand_total": order.grand_total,
        "created_at": order.created_at,
        "approved_at": order.approved_at,
    }


def list_orders(db: Session, status: str | None) -> list[OrderSummaryOut]:
    return [OrderSummaryOut(**_order_summary_fields(o)) for o in repository.list_orders(db, status)]


def get_order_detail(db: Session, order_ref: str) -> OrderDetailOut:
    order = repository.find_order(db, order_ref)
    if order is None:
        raise AppException(
            "Order not found", ErrorCode.RESOURCE_NOT_FOUND, 404, {"order": order_ref}
        )
    return OrderDetailOut(
        **_order_summary_fields(order),
        created_by=order.created_by,
        ai_extraction_id=order.ai_extraction_id,
        remarks=order.remarks,
        rejection_reason=order.rejection_reason,
        approved_by=order.approved_by,
        items=[OrderItemOut.model_validate(i) for i in order.items],
        corrections=[
            CorrectionOut.model_validate(c)
            for c in repository.list_corrections(db, [i.id for i in order.items])
        ],
        stock_movements=[
            StockMovementOut.model_validate(m) for m in repository.list_stock_movements(db, order_id=order.id)
        ],
        ledger_entries=[
            LedgerEntryOut.model_validate(e) for e in repository.list_ledger_entries(db, order_id=order.id)
        ],
    )


def list_extractions(db: Session) -> list[ExtractionOut]:
    order_numbers = repository.order_numbers_by_extraction(db)
    return [
        ExtractionOut(
            id=e.id,
            retailer_id=e.retailer_id,
            user_id=e.user_id,
            original_message=e.original_message,
            extraction_status=e.extraction_status,
            model_name=e.model_name,
            created_at=e.created_at,
            order_number=order_numbers.get(e.id),
            items=[ExtractionItemOut.model_validate(i) for i in e.items],
        )
        for e in repository.list_extractions(db)
    ]


def list_inventory(db: Session) -> list[InventoryOut]:
    return [
        InventoryOut(
            product_id=product.id,
            sku=product.sku,
            name=product.name,
            stock_cases=inventory.stock_cases,
            movements=[
                StockMovementOut.model_validate(m)
                for m in repository.list_stock_movements(db, product_id=product.id)
            ],
        )
        for inventory, product in repository.list_inventory(db)
    ]


def get_retailer_credit(db: Session, retailer_id: uuid.UUID) -> CreditDetailOut:
    retailer = repository.get_retailer(db, retailer_id)
    account = repository.get_credit_account(db, retailer_id) if retailer else None
    if retailer is None or account is None:
        raise AppException(
            "Retailer or credit account not found", ErrorCode.RESOURCE_NOT_FOUND, 404,
            {"retailer_id": str(retailer_id)},
        )
    return CreditDetailOut(
        retailer_id=retailer.id,
        shop_name=retailer.shop_name,
        credit_limit=account.credit_limit,
        current_outstanding=account.current_outstanding,
        available_credit=account.credit_limit - account.current_outstanding,
        ledger=[
            LedgerEntryOut.model_validate(e)
            for e in repository.list_ledger_entries(db, retailer_id=retailer_id)
        ],
    )


def check_integrity(db: Session) -> IntegrityOut:
    checks = [
        IntegrityCheckOut(name=name, passed=not problems, problems=problems)
        for name, problems in repository.run_integrity_queries(db).items()
    ]
    return IntegrityOut(all_passed=all(c.passed for c in checks), checks=checks)
