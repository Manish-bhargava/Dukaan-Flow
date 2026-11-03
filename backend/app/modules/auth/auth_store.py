"""Temporary authentication state in Upstash Redis (REST API): OTPs and rate limits.

Keys (all expire on their own; {phone} is the 10-digit mobile number):
  otp:{phone}             keyed hash of the current OTP              TTL OTP_EXPIRE_SECONDS (120)
  otp_attempts:{phone}    failed verifications of the current OTP    expires with the OTP
  otp_cooldown:{phone}    blocks resending                           TTL OTP_RESEND_COOLDOWN_SECONDS (60)
  otp_requests:{phone}    OTP requests in the current window         TTL OTP_REQUEST_WINDOW_SECONDS (900)
  login_attempts:{phone}  password attempts in the current window    TTL LOGIN_WINDOW_SECONDS (900)

Every operation is one Lua script, which Redis runs atomically, so concurrent requests
cannot consume an OTP twice or get past a limit. Saving a new OTP never touches
otp_requests, so resending cannot reset the request limit.
"""

import logging
from enum import StrEnum
from functools import lru_cache
from typing import Any, Protocol

from upstash_redis import Redis

from app.core.config import settings
from app.core.constants import ErrorCode
from app.exceptions.base import AppException

logger = logging.getLogger(__name__)

# Rate limit for OTP requests: 60 s cooldown, then at most N requests per window.
# Returns {status, retry_after_seconds}.
_RESERVE_OTP_REQUEST = """
local cooldown = redis.call('TTL', KEYS[1])
if cooldown > 0 then
  return {'COOLDOWN', cooldown}
end
local count = tonumber(redis.call('GET', KEYS[2]) or '0')
if count >= tonumber(ARGV[2]) then
  local ttl = redis.call('TTL', KEYS[2])
  if ttl < 1 then ttl = tonumber(ARGV[3]) end
  return {'LIMITED', ttl}
end
count = redis.call('INCR', KEYS[2])
if count == 1 then
  redis.call('EXPIRE', KEYS[2], tonumber(ARGV[3]))
end
redis.call('SET', KEYS[1], '1', 'EX', tonumber(ARGV[1]))
return {'OK', 0}
"""

# Store a new OTP (replacing any older one) and reset its failed-attempt counter.
_SAVE_OTP = """
redis.call('SET', KEYS[1], ARGV[1], 'EX', tonumber(ARGV[2]))
redis.call('DEL', KEYS[2])
return 1
"""

# Check an OTP hash. Returns {status, remaining_attempts}.
_VERIFY_OTP = """
local stored = redis.call('GET', KEYS[1])
if not stored then
  return {'EXPIRED', 0}
end
local max_attempts = tonumber(ARGV[2])
local attempts = tonumber(redis.call('GET', KEYS[2]) or '0')
if attempts >= max_attempts then
  redis.call('DEL', KEYS[1], KEYS[2])
  return {'LOCKED', 0}
end
if stored == ARGV[1] then
  redis.call('DEL', KEYS[1], KEYS[2])
  return {'OK', max_attempts - attempts}
end
attempts = redis.call('INCR', KEYS[2])
local ttl = redis.call('PTTL', KEYS[1])
if ttl > 0 then
  redis.call('PEXPIRE', KEYS[2], ttl)
end
if attempts >= max_attempts then
  redis.call('DEL', KEYS[1], KEYS[2])
  return {'LOCKED', 0}
end
return {'INVALID', max_attempts - attempts}
"""

_DELETE_OTP = """
redis.call('DEL', KEYS[1], KEYS[2])
return 1
"""

# Count a password attempt BEFORE the password is checked, so concurrent requests cannot
# all pass a check-then-increment. Returns {status, retry_after_seconds}.
_RESERVE_LOGIN_ATTEMPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
end
if count > tonumber(ARGV[1]) then
  local ttl = redis.call('TTL', KEYS[1])
  if ttl < 1 then ttl = tonumber(ARGV[2]) end
  return {'LIMITED', ttl}
end
return {'OK', 0}
"""

_CLEAR_LOGIN_ATTEMPTS = """
redis.call('DEL', KEYS[1])
return 1
"""


class OtpCheck(StrEnum):
    OK = "OK"
    INVALID = "INVALID"
    EXPIRED = "EXPIRED"  # expired, never requested, already used, or locked earlier
    LOCKED = "LOCKED"  # attempt limit reached; the OTP has been deleted


class RateLimit(StrEnum):
    OK = "OK"
    COOLDOWN = "COOLDOWN"  # OTP resend cooldown
    LIMITED = "LIMITED"  # too many requests/attempts in the window


class RedisClient(Protocol):
    def eval(self, script: str, keys: list[str] | None = None, args: list[str] | None = None) -> Any: ...


def _unavailable() -> AppException:
    return AppException(
        "Authentication service is temporarily unavailable. Please try again.",
        ErrorCode.AUTH_SERVICE_UNAVAILABLE,
        503,
    )


class AuthStore:
    def __init__(self, client: RedisClient | None):
        # None when Upstash is not configured: every operation then fails with 503.
        self._client = client

    def _eval(self, script: str, keys: list[str], args: list[Any] | None = None) -> Any:
        if self._client is None:
            logger.error("UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN are not set")
            raise _unavailable()
        try:
            return self._client.eval(script, keys=keys, args=[str(a) for a in args or []])
        except Exception as exc:  # network errors, UpstashError, timeouts
            logger.error("Redis operation failed: %s", exc)
            raise _unavailable() from exc

    @staticmethod
    def _otp_keys(phone: str) -> list[str]:
        return [f"otp:{phone}", f"otp_attempts:{phone}"]

    def reserve_otp_request(
        self, phone: str, cooldown_seconds: int, max_requests: int, window_seconds: int
    ) -> tuple[RateLimit, int]:
        status, retry_after = self._eval(
            _RESERVE_OTP_REQUEST,
            [f"otp_cooldown:{phone}", f"otp_requests:{phone}"],
            [cooldown_seconds, max_requests, window_seconds],
        )
        return RateLimit(status), int(retry_after)

    def save_otp(self, phone: str, otp_hash: str, ttl_seconds: int) -> None:
        self._eval(_SAVE_OTP, self._otp_keys(phone), [otp_hash, ttl_seconds])

    def verify_otp(self, phone: str, otp_hash: str, max_attempts: int) -> tuple[OtpCheck, int]:
        status, remaining = self._eval(_VERIFY_OTP, self._otp_keys(phone), [otp_hash, max_attempts])
        return OtpCheck(status), int(remaining)

    def invalidate_otp(self, phone: str) -> None:
        self._eval(_DELETE_OTP, self._otp_keys(phone))

    def reserve_login_attempt(
        self, phone: str, max_attempts: int, window_seconds: int
    ) -> tuple[RateLimit, int]:
        status, retry_after = self._eval(
            _RESERVE_LOGIN_ATTEMPT, [f"login_attempts:{phone}"], [max_attempts, window_seconds]
        )
        return RateLimit(status), int(retry_after)

    def clear_login_attempts(self, phone: str) -> None:
        self._eval(_CLEAR_LOGIN_ATTEMPTS, [f"login_attempts:{phone}"])


@lru_cache
def _upstash_client(url: str, token: str) -> Redis:
    return Redis(url=url, token=token, rest_retries=1, rest_retry_interval=0.5, allow_telemetry=False)


def get_auth_store() -> AuthStore:
    """FastAPI dependency. Without Upstash credentials, operations fail with 503 when used."""
    if not settings.UPSTASH_REDIS_REST_URL or not settings.UPSTASH_REDIS_REST_TOKEN:
        return AuthStore(None)
    return AuthStore(_upstash_client(settings.UPSTASH_REDIS_REST_URL, settings.UPSTASH_REDIS_REST_TOKEN))
