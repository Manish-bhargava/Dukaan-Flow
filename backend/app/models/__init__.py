"""Import every model here so Base.metadata is complete (used by Alembic autogenerate)."""

from app.models.ai_order import AiExtraction, AiExtractionItem, RetailerAlias
from app.models.catalog import Category, Product
from app.models.credit import CreditAccount, CreditLedger
from app.models.inventory import Inventory, StockMovement
from app.models.order import Order, OrderCorrection, OrderItem
from app.models.pricing import RetailerPrice, Scheme
from app.models.retailer import Retailer
from app.models.user import OtpVerification, User

__all__ = [
    "AiExtraction",
    "AiExtractionItem",
    "Category",
    "CreditAccount",
    "CreditLedger",
    "Inventory",
    "OrderCorrection",
    "Order",
    "OrderItem",
    "OtpVerification",
    "Product",
    "Retailer",
    "RetailerAlias",
    "RetailerPrice",
    "Scheme",
    "StockMovement",
    "User",
]
