"""Phone + OTP login (RETAILER only; the OTP is emailed to the account's registered email)
and phone + password login (SALESMAN, ORDER_DESK, ADMIN). Both return the same JWT.

Phone numbers are not revealed: send-otp answers every valid number the same way, rate
limits apply to every number before any account lookup, and password login gives one
error for unknown numbers, wrong passwords and accounts that use OTP. The one exception
is an email that cannot be sent, which returns 503 so success is never reported falsely.
Logs never contain the OTP, the API key or the JWT.
"""

import logging
from datetime import UTC, datetime

import anyio
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import OTP_LOGIN_ROLES, PASSWORD_LOGIN_ROLES, ErrorCode
from app.core.security import create_access_token, generate_otp, hash_otp, verify_password
from app.exceptions.base import AppException
from app.models import User
from app.modules.auth import repository
from app.modules.auth.auth_store import AuthStore, OtpCheck, RateLimit
from app.modules.auth.schemas import AuthUserOut, TokenOut
from app.modules.auth.mailer import EmailDeliveryError, mask_email, send_otp_email

logger = logging.getLogger(__name__)

OTP_REQUEST_MESSAGE = "If this number is registered, an OTP will be sent to the email address on the account."


def _account_disabled() -> AppException:
    return AppException("This account has been deactivated", ErrorCode.ACCOUNT_DISABLED, 403)


def _rate_limited(message: str, reason: str, retry_after: int) -> AppException:
    return AppException(
        message,
        ErrorCode.RATE_LIMIT_EXCEEDED,
        429,
        details={"reason": reason, "retry_after": retry_after},
        headers={"Retry-After": str(retry_after)},
    )


def _delivery_failed() -> AppException:
    return AppException(
        "We could not send the OTP. Please try again later.", ErrorCode.OTP_DELIVERY_FAILED, 503
    )


def _record_login(db: Session, user: User) -> None:
    """users.last_login_at, for the Admin's user activity view."""
    user.last_login_at = datetime.now(UTC)
    db.commit()


def issue_token(user: User) -> TokenOut:
    token, expires_in = create_access_token(user)
    return TokenOut(access_token=token, expires_in=expires_in, user=AuthUserOut.model_validate(user))


def request_otp(db: Session, store: AuthStore, phone: str) -> None:
    """Rate-limit the request, then create and email an OTP only for an active retailer.

    Unknown, inactive and non-retailer numbers get the same response as a successful send.
    If the retailer has no email, or Brevo does not accept the email, no usable OTP is left
    in Redis and 503 OTP_DELIVERY_FAILED is returned.
    """
    status, retry_after = store.reserve_otp_request(
        phone,
        settings.OTP_RESEND_COOLDOWN_SECONDS,
        settings.OTP_MAX_REQUESTS,
        settings.OTP_REQUEST_WINDOW_SECONDS,
    )
    if status == RateLimit.COOLDOWN:
        raise _rate_limited("Please wait before requesting another OTP.", "RESEND_COOLDOWN", retry_after)
    if status == RateLimit.LIMITED:
        raise _rate_limited("Too many OTP requests. Please try again later.", "OTP_REQUEST_LIMIT", retry_after)

    user = repository.get_user_by_phone(db, phone)
    if user is None or not user.is_active or user.role not in OTP_LOGIN_ROLES:
        # Server-side only; the caller still gets the generic response.
        logger.info("No OTP sent for %s: not an active retailer account", phone)
        return
    if not user.email:
        logger.warning("No OTP sent for %s: retailer %s has no registered email address", phone, user.id)
        raise _delivery_failed()

    otp = generate_otp()
    logger.info("[OTP] OTP generated for user %s", user.id)
    # TEMPORARY OTP debugging logs (never the OTP, its hash, the email or credentials).
    logger.info("[OTP] Redis key: otp:%s", phone)
    logger.info("[OTP] Redis SET operation started (TTL %ss)", settings.OTP_EXPIRE_SECONDS)
    store.save_otp(phone, hash_otp(phone, otp), settings.OTP_EXPIRE_SECONDS)
    logger.info("[OTP] Redis SET operation successful")
    exists, ttl = store.otp_state(phone)
    logger.info("[OTP] Redis check after SET: EXISTS=%s TTL=%ss", int(exists), ttl)
    try:
        # The mailer is async; this sync endpoint runs in a worker thread, so the send is
        # awaited on the server's event loop without blocking it.
        anyio.from_thread.run(send_otp_email, user.email, otp)
    except Exception as exc:
        # Never leave a usable OTP the user did not receive. The reason is logged (never the OTP).
        logger.error(
            "OTP email to %s for user %s could not be sent: %s",
            mask_email(user.email),
            user.id,
            exc,
            exc_info=not isinstance(exc, EmailDeliveryError),
        )
        logger.warning("[OTP] Email delivery FAILED; deleting otp:%s so no undelivered OTP stays usable", phone)
        store.invalidate_otp(phone)
        logger.info("[OTP] OTP deleted from Redis: otp:%s (reason: email not delivered)", phone)
        raise _delivery_failed() from None
    logger.info("[OTP] Email delivery successful via %s (to %s, user %s)", settings.EMAIL_PROVIDER, mask_email(user.email), user.id)
    exists, ttl = store.otp_state(phone)
    logger.info("[OTP] Redis check after email: EXISTS=%s TTL=%ss", int(exists), ttl)


def verify_otp(db: Session, store: AuthStore, phone: str, otp: str) -> TokenOut:
    status, remaining = store.verify_otp(phone, hash_otp(phone, otp), settings.OTP_MAX_ATTEMPTS)
    logger.info("[OTP] Verification for otp:%s: %s (remaining attempts %s)", phone, status, remaining)
    if status == OtpCheck.OK:
        logger.info("[OTP] OTP deleted from Redis: otp:%s (reason: verified successfully)", phone)
    elif status == OtpCheck.LOCKED:
        logger.info("[OTP] OTP deleted from Redis: otp:%s (reason: too many wrong attempts)", phone)
    elif status == OtpCheck.EXPIRED:
        logger.info("[OTP] No OTP in Redis for otp:%s (expired, already used or never stored)", phone)
    if status == OtpCheck.EXPIRED:
        raise AppException(
            "OTP has expired or is no longer valid. Please request a new OTP.",
            ErrorCode.OTP_EXPIRED,
            401,
        )
    if status == OtpCheck.LOCKED:
        raise AppException(
            "Too many incorrect attempts. Please request a new OTP.",
            ErrorCode.OTP_ATTEMPTS_EXCEEDED,
            429,
        )
    if status == OtpCheck.INVALID:
        raise AppException(
            "Incorrect OTP", ErrorCode.INVALID_OTP, 401, {"remaining_attempts": remaining}
        )

    # OTPs are only issued to active retailers; recheck in case the account changed since.
    user = repository.get_user_by_phone(db, phone)
    if user is None or user.role not in OTP_LOGIN_ROLES:
        raise AppException("OTP login is not available for this account", ErrorCode.UNAUTHORIZED, 401)
    if not user.is_active:
        raise _account_disabled()
    logger.info("OTP login successful for user %s", user.id)
    _record_login(db, user)
    return issue_token(user)


def login_with_password(db: Session, store: AuthStore, phone: str, password: str) -> TokenOut:
    """Internal users only. Every attempt is counted (atomically, before the password is
    checked); a successful login clears the count."""
    status, retry_after = store.reserve_login_attempt(
        phone, settings.LOGIN_MAX_ATTEMPTS, settings.LOGIN_WINDOW_SECONDS
    )
    if status != RateLimit.OK:
        raise _rate_limited("Too many login attempts. Please try again later.", "LOGIN_ATTEMPTS", retry_after)

    user = repository.get_user_by_phone(db, phone)
    password_ok = verify_password(password, user.password_hash if user else None)
    if user is None or not password_ok or user.role not in PASSWORD_LOGIN_ROLES:
        raise AppException("Invalid phone number or password", ErrorCode.INVALID_CREDENTIALS, 401)
    if not user.is_active:
        raise _account_disabled()

    store.clear_login_attempts(phone)
    _record_login(db, user)
    return issue_token(user)
