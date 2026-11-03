import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.constants import ErrorCode, UserRole
from app.core.permissions import ensure_role
from app.core.security import decode_access_token
from app.database.session import get_db
from app.exceptions.base import AppException
from app.models import User
from app.modules.auth import repository as auth_repository

# Shared FastAPI dependency aliases for route handlers.
DbSession = Annotated[Session, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Authenticate the request from its Bearer token and load the user from PostgreSQL.

    The token's role must still match the stored role, and the account must be active,
    so deactivations and role changes take effect immediately.
    """
    if credentials is None:
        raise AppException("Authentication required", ErrorCode.UNAUTHORIZED, 401)
    claims = decode_access_token(credentials.credentials)
    try:
        user_id = uuid.UUID(str(claims["sub"]))
    except ValueError:
        raise AppException("Invalid access token", ErrorCode.UNAUTHORIZED, 401) from None
    user = auth_repository.get_user_by_id(db, user_id)
    if user is None or user.role != claims["role"]:
        raise AppException("Access token is no longer valid", ErrorCode.UNAUTHORIZED, 401)
    if not user.is_active:
        raise AppException("This account has been deactivated", ErrorCode.ACCOUNT_DISABLED, 403)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    """Dependency factory: `user: Annotated[User, Depends(require_roles(UserRole.ADMIN))]`.
    Resource ownership is still checked in the services via app/core/permissions.py."""

    def dependency(user: CurrentUser) -> User:
        ensure_role(user, *roles)
        return user

    return dependency
