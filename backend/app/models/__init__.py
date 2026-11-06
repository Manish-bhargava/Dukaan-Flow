"""Import every model here so Base.metadata is complete (used by Alembic autogenerate)."""

from app.models.admin import AppSetting, AuditLog, SalesmanSyncStatus
from app.models.ai_order import AiExtraction, AiExtractionItem, RetailerAlias
from app.models.catalog import Brand, Category, Product
from app.models.credit import CreditAccount, CreditLedger
from app.models.inventory import Inventory, StockMovement
from app.models.order import Order, OrderCorrection, OrderEvent, OrderItem
from app.models.pricing import RetailerPrice, Scheme
from app.models.retailer import Retailer
from app.models.user import OtpVerification, User
from app.models.visit import ShopVisit

__all__ = [
    "AiExtraction",
    "AppSetting",
    "AuditLog",
    "Brand",
    "AiExtractionItem",
    "Category",
    "CreditAccount",
    "CreditLedger",
    "Inventory",
    "OrderCorrection",
    "Order",
    "OrderEvent",
    "OrderItem",
    "OtpVerification",
    "Product",
    "Retailer",
    "RetailerAlias",
    "RetailerPrice",
    "SalesmanSyncStatus",
    "Scheme",
    "ShopVisit",
    "StockMovement",
    "User",
]
