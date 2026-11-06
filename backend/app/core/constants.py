from enum import StrEnum


class ErrorCode:
    """Error codes returned in the standard error response (see docs/API_DESIGN.MD)."""

    UNAUTHORIZED = "UNAUTHORIZED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    ACCOUNT_DISABLED = "ACCOUNT_DISABLED"
    INVALID_OTP = "INVALID_OTP"
    OTP_EXPIRED = "OTP_EXPIRED"
    OTP_ATTEMPTS_EXCEEDED = "OTP_ATTEMPTS_EXCEEDED"
    AUTH_SERVICE_UNAVAILABLE = "AUTH_SERVICE_UNAVAILABLE"
    OTP_DELIVERY_FAILED = "OTP_DELIVERY_FAILED"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    FORBIDDEN = "FORBIDDEN"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    HTTP_ERROR = "HTTP_ERROR"
    PRODUCT_NOT_FOUND = "PRODUCT_NOT_FOUND"
    AMBIGUOUS_PRODUCT = "AMBIGUOUS_PRODUCT"
    PRICE_NOT_AVAILABLE = "PRICE_NOT_AVAILABLE"
    SCHEME_CONFLICT = "SCHEME_CONFLICT"
    INSUFFICIENT_STOCK = "INSUFFICIENT_STOCK"
    CREDIT_LIMIT_EXCEEDED = "CREDIT_LIMIT_EXCEEDED"
    INVALID_ORDER_STATUS = "INVALID_ORDER_STATUS"
    INVALID_EXTRACTION_STATUS = "INVALID_EXTRACTION_STATUS"
    ORDER_DATA_CHANGED = "ORDER_DATA_CHANGED"
    NOTHING_TO_EXPORT = "NOTHING_TO_EXPORT"
    ORDERING_RESTRICTED = "ORDERING_RESTRICTED"
    CONFLICT = "CONFLICT"
    AI_NOT_CONFIGURED = "AI_NOT_CONFIGURED"
    AI_SERVICE_UNAVAILABLE = "AI_SERVICE_UNAVAILABLE"
    IMAGE_STORAGE_NOT_CONFIGURED = "IMAGE_STORAGE_NOT_CONFIGURED"
    IMAGE_UPLOAD_FAILED = "IMAGE_UPLOAD_FAILED"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"


# Allowed values for VARCHAR status/type columns. Enforced in the database by CHECK constraints.


class UserRole(StrEnum):
    RETAILER = "RETAILER"
    SALESMAN = "SALESMAN"
    ORDER_DESK = "ORDER_DESK"
    ADMIN = "ADMIN"


class PriceBasis(StrEnum):
    CASE = "CASE"
    PIECE = "PIECE"


class SchemeType(StrEnum):
    FREE_GOODS = "FREE_GOODS"
    SLAB_DISCOUNT = "SLAB_DISCOUNT"


class ExtractionStatus(StrEnum):
    PENDING = "PENDING"
    REVIEWED = "REVIEWED"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"


class AiInputType(StrEnum):
    TEXT = "TEXT"
    IMAGE = "IMAGE"  # photo of a handwritten / printed order list
    VOICE = "VOICE"  # voice note, transcribed before extraction


class OrderSource(StrEnum):
    MANUAL = "MANUAL"
    AI = "AI"
    SALESMAN = "SALESMAN"


class OrderStatus(StrEnum):
    PENDING = "PENDING"
    CREDIT_HOLD = "CREDIT_HOLD"
    ON_HOLD = "ON_HOLD"  # needs review: offline order whose data changed, or held by the desk (hold_reason)
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"  # desk asked the retailer/salesman (clarification_message)
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class OrderEventAction(StrEnum):
    """Order history (order_events), one row per important action."""

    RECEIVED = "RECEIVED"
    CONFIRMED = "CONFIRMED"
    CREDIT_HOLD = "CREDIT_HOLD"
    PUT_ON_HOLD = "PUT_ON_HOLD"
    CLARIFICATION_REQUESTED = "CLARIFICATION_REQUESTED"
    CORRECTED = "CORRECTED"
    REJECTED = "REJECTED"
    EXPORTED = "EXPORTED"


class VisitOutcome(StrEnum):
    ORDER_PLACED = "ORDER_PLACED"
    NO_ORDER = "NO_ORDER"


class StockMovementType(StrEnum):
    ORDER_DEDUCTION = "ORDER_DEDUCTION"
    RESTOCK = "RESTOCK"
    ADJUSTMENT = "ADJUSTMENT"


class CreditTransactionType(StrEnum):
    ORDER_DEBIT = "ORDER_DEBIT"
    PAYMENT_CREDIT = "PAYMENT_CREDIT"
    ADJUSTMENT = "ADJUSTMENT"


# Roles allowed to review, correct, approve and reject orders.
ORDER_DESK_ROLES = (UserRole.ORDER_DESK, UserRole.ADMIN)

# Orders can only be corrected, approved or rejected while in one of these statuses.
OPEN_ORDER_STATUSES = (
    OrderStatus.PENDING, OrderStatus.CREDIT_HOLD, OrderStatus.ON_HOLD, OrderStatus.CLARIFICATION_REQUIRED,
)
# Open orders that hold the retailer's credit while they wait (CREDIT_HOLD is already above it).
CREDIT_RESERVING_STATUSES = (OrderStatus.PENDING, OrderStatus.ON_HOLD, OrderStatus.CLARIFICATION_REQUIRED)

# Login methods by role: retailers use phone + OTP only; internal users use phone + password only.
OTP_LOGIN_ROLES = (UserRole.RETAILER,)
PASSWORD_LOGIN_ROLES = (UserRole.SALESMAN, UserRole.ORDER_DESK, UserRole.ADMIN)
