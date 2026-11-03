"""Password hashing, OTP generation/hashing and JWT access tokens."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import settings
from app.core.constants import ErrorCode
from app.exceptions.base import AppException
from app.models import User

# Argon2id with argon2-cffi's defaults (RFC 9106 low-memory profile).
_password_hasher = PasswordHasher()
# Verified against when a user has no password, so response time does not reveal it.
_DUMMY_HASH = _password_hasher.hash("timing-equalisation-only")


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _password_hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def generate_otp() -> str:
    """Cryptographically random 6-digit OTP."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(recipient: str, otp: str) -> str:
    """Keyed hash (HMAC-SHA256), bound to the recipient (phone number), so a leaked Redis
    value cannot be brute-forced offline or used for another account."""
    key = hashlib.sha256(b"dukaanflow-otp:" + settings.JWT_SECRET_KEY.encode()).digest()
    return hmac.new(key, f"{recipient}:{otp}".encode(), hashlib.sha256).hexdigest()


def create_access_token(user: User) -> tuple[str, int]:
    """The single token format used by every login method. Returns (token, expires_in seconds)."""
    now = datetime.now(UTC)
    expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM), expires_in


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify signature and expiry; raise 401 with UNAUTHORIZED or TOKEN_EXPIRED."""
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "role", "exp"]},
        )
    except jwt.ExpiredSignatureError:
        raise AppException("Access token has expired", ErrorCode.TOKEN_EXPIRED, 401) from None
    except jwt.InvalidTokenError:
        raise AppException("Invalid access token", ErrorCode.UNAUTHORIZED, 401) from None
