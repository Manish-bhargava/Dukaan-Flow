"""Role and data-ownership checks. Every service that touches retailer data calls these
with the acting user, so access rules are enforced on the backend regardless of the caller.
"""

import uuid

from app.core.constants import ErrorCode, UserRole
from app.exceptions.base import AppException
from app.models import Retailer, User


def forbidden(message: str = "You do not have permission to perform this action") -> AppException:
    return AppException(message, ErrorCode.FORBIDDEN, status_code=403)


def ensure_role(actor: User, *roles: UserRole) -> None:
    if not actor.is_active or actor.role not in roles:
        raise forbidden()


def can_access_retailer(actor: User, retailer: Retailer) -> bool:
    """RETAILER: own shop only. SALESMAN: assigned shops only. ORDER_DESK/ADMIN: all."""
    if not actor.is_active:
        return False
    if actor.role == UserRole.RETAILER:
        return actor.retailer_id == retailer.id
    if actor.role == UserRole.SALESMAN:
        return retailer.assigned_salesman_id == actor.id
    return actor.role in (UserRole.ORDER_DESK, UserRole.ADMIN)


def ensure_can_access_retailer(actor: User, retailer: Retailer) -> None:
    if not can_access_retailer(actor, retailer):
        raise forbidden("You do not have access to this retailer's data")


def visible_retailer_ids(actor: User, assigned_retailer_ids: list[uuid.UUID]) -> list[uuid.UUID] | None:
    """Retailer IDs the actor may list data for; None means all retailers."""
    if not actor.is_active:
        raise forbidden()
    if actor.role == UserRole.RETAILER:
        return [actor.retailer_id] if actor.retailer_id else []
    if actor.role == UserRole.SALESMAN:
        return assigned_retailer_ids
    return None
