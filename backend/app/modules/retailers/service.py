import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.constants import OPEN_ORDER_STATUSES, ErrorCode, OrderStatus, UserRole
from app.core.permissions import ensure_can_access_retailer, ensure_role
from app.exceptions.base import AppException
from app.models import CreditAccount, Retailer, User
from app.modules.retailers import repository


@dataclass(frozen=True)
class CreditSummary:
    credit_limit: Decimal
    current_outstanding: Decimal  # confirmed orders not yet paid
    reserved_for_review: Decimal  # open orders awaiting the Order Desk
    available_credit: Decimal  # credit_limit - current_outstanding - reserved_for_review


def available_credit(account: CreditAccount | None, reserved: Decimal = Decimal("0")) -> Decimal:
    """credit_limit - current_outstanding - credit held by open orders; no account = no credit."""
    if account is None:
        return Decimal("0")
    return account.credit_limit - account.current_outstanding - Decimal(reserved)


def credit_available(db: Session, retailer_id: uuid.UUID, exclude_order_id: uuid.UUID | None = None,
                     account: CreditAccount | None = None) -> Decimal:
    """Available credit right now: open orders (except `exclude_order_id`) hold their total."""
    if account is None:
        account = repository.get_credit_account(db, retailer_id)
    return available_credit(account, repository.reserved_credit(db, retailer_id, exclude_order_id))


def credit_summary(db: Session, account: CreditAccount) -> CreditSummary:
    reserved = Decimal(repository.reserved_credit(db, account.retailer_id))
    return CreditSummary(
        credit_limit=account.credit_limit,
        current_outstanding=account.current_outstanding,
        reserved_for_review=reserved,
        available_credit=available_credit(account, reserved),
    )


def get_retailer_for(db: Session, actor: User, retailer_id: uuid.UUID) -> Retailer:
    """Load a retailer the actor is allowed to see (404 if missing, 403 if not theirs)."""
    retailer = repository.get_retailer(db, retailer_id)
    if retailer is None:
        raise AppException(
            "Retailer not found", ErrorCode.RESOURCE_NOT_FOUND, 404,
            {"retailer_id": str(retailer_id)},
        )
    ensure_can_access_retailer(actor, retailer)
    return retailer


def get_credit_summary(db: Session, actor: User, retailer_id: uuid.UUID) -> CreditSummary:
    """Read-only credit view. There is deliberately no service that lets a retailer change
    its own credit limit or outstanding balance."""
    retailer = get_retailer_for(db, actor, retailer_id)
    account = repository.get_credit_account(db, retailer.id)
    if account is None:
        raise AppException("Credit account not found", ErrorCode.RESOURCE_NOT_FOUND, 404)
    return credit_summary(db, account)


@dataclass(frozen=True)
class PurchaseSummary:
    total_orders: int  # every order placed, any status
    confirmed_orders: int  # APPROVED
    total_purchased: Decimal  # sum of APPROVED orders' grand totals (rejected never count)
    under_review_orders: int  # PENDING, CREDIT_HOLD, ON_HOLD: placed, not yet accepted
    under_review_amount: Decimal
    rejected_orders: int


@dataclass(frozen=True)
class RetailerProfile:
    retailer: Retailer
    credit: CreditSummary | None
    purchases: PurchaseSummary


def get_my_profile(db: Session, actor: User) -> RetailerProfile:
    """The signed-in retailer's shop details, credit position and purchase summary."""
    ensure_role(actor, UserRole.RETAILER)
    if actor.retailer_id is None:
        raise AppException("No retailer is linked to this account", ErrorCode.FORBIDDEN, 403)
    retailer = get_retailer_for(db, actor, actor.retailer_id)
    account = repository.get_credit_account(db, retailer.id)
    stats = repository.order_stats(db, retailer.id)

    def count(*statuses: str) -> int:
        return sum(stats.get(s, (0, 0))[0] for s in statuses)

    def amount(*statuses: str) -> Decimal:
        return sum((Decimal(stats.get(s, (0, 0))[1]) for s in statuses), Decimal("0"))

    return RetailerProfile(
        retailer=retailer,
        credit=None if account is None else credit_summary(db, account),
        purchases=PurchaseSummary(
            total_orders=sum(c for c, _ in stats.values()),
            confirmed_orders=count(OrderStatus.APPROVED),
            total_purchased=amount(OrderStatus.APPROVED),
            under_review_orders=count(*OPEN_ORDER_STATUSES),
            under_review_amount=amount(*OPEN_ORDER_STATUSES),
            rejected_orders=count(OrderStatus.REJECTED),
        ),
    )
