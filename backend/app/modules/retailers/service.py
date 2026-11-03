import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.constants import ErrorCode
from app.core.permissions import ensure_can_access_retailer
from app.exceptions.base import AppException
from app.models import CreditAccount, Retailer, User
from app.modules.retailers import repository


@dataclass(frozen=True)
class CreditSummary:
    credit_limit: Decimal
    current_outstanding: Decimal
    available_credit: Decimal


def available_credit(account: CreditAccount | None) -> Decimal:
    """credit_limit - current_outstanding; a retailer without an account has no credit."""
    if account is None:
        return Decimal("0")
    return account.credit_limit - account.current_outstanding


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
    return CreditSummary(
        credit_limit=account.credit_limit,
        current_outstanding=account.current_outstanding,
        available_credit=available_credit(account),
    )
