"""Authentication: phone OTP login with the OTP emailed to the account (Redis + Lua), rate
limits, password login, JWT and authorization. Upstash is replaced by fakeredis (same Lua
scripts); emails are captured.
"""

import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import fakeredis
import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.core.constants import UserRole
from app.core.dependencies import CurrentUser, require_roles
from app.core.security import create_access_token, hash_otp, hash_password
from app.database.session import get_db
from app.exceptions.handlers import register_exception_handlers
from app.main import app
from app.models import User
from app.modules.auth import auth_store as auth_store_module
from app.modules.auth import service as auth_service
from app.modules.auth import mailer as mailer_module
from app.modules.auth.auth_store import AuthStore, OtpCheck, RateLimit, get_auth_store
from app.modules.retailers import service as retailers_service
from seed.run_seed import seed_id
from tests.conftest import seed_user

SHARMA_PHONE, GUPTA_PHONE = "9000000101", "9000000102"  # retailers
SHARMA_EMAIL, GUPTA_EMAIL = "sharma.kirana@example.com", "gupta.general@example.com"  # their emails
DESK_PHONE, ADMIN_PHONE = "9000000002", "9000000001"  # internal users
UNKNOWN_PHONE = "9999999999"
PASSWORD = "correct horse battery staple"
GENERIC_MESSAGE = "If this number is registered, an OTP will be sent to the email address on the account."


class FakeUpstash:
    """Same eval() signature as upstash_redis.Redis, backed by fakeredis (real Lua)."""

    def __init__(self):
        self.r = fakeredis.FakeRedis(decode_responses=True)

    def eval(self, script, keys=None, args=None):
        keys, args = keys or [], args or []
        return self.r.eval(script, len(keys), *keys, *args)

    def end_cooldown(self, phone):
        """Simulate the 60-second resend cooldown passing."""
        self.r.delete(f"otp_cooldown:{phone}")


class BrokenUpstash:
    def eval(self, script, keys=None, args=None):
        raise ConnectionError("simulated: Upstash unreachable")


@pytest.fixture
def redis():
    return FakeUpstash()


@pytest.fixture
def outbox(monkeypatch):
    """Captures OTP emails instead of sending them; returns {email: [otp, ...]}."""
    sent: dict[str, list[str]] = {}

    async def capture(email, otp):
        sent.setdefault(email, []).append(otp)

    monkeypatch.setattr(auth_service, "send_otp_email", capture)
    return sent


@pytest.fixture
def api(tx_client, redis, outbox):
    app.dependency_overrides[get_auth_store] = lambda: AuthStore(redis)
    return tx_client


@pytest.fixture
def staff_password(tx):
    for key in ("order_desk", "admin", "salesman_sunil"):
        seed_user(tx, key).password_hash = hash_password(PASSWORD)
    tx.flush()


def send(client, phone):
    return client.post("/api/v1/auth/send-otp", json={"phone": phone})


def verify(client, phone, otp):
    return client.post("/api/v1/auth/verify-otp", json={"phone": phone, "otp": otp})


def login(client, phone, password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"phone": phone, "password": password})


def wrong(otp: str) -> str:
    return f"{(int(otp) + 1) % 1_000_000:06d}"


def claims(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def error(response) -> tuple[int, str]:
    return response.status_code, response.json()["error_code"]


# ---------------------------------------------------------------- send-otp


def test_send_otp_to_retailer_stores_hashed_otp_with_120_second_ttl(api, redis, outbox):
    response = send(api, SHARMA_PHONE)
    assert response.status_code == 200
    assert response.json()["message"] == GENERIC_MESSAGE
    assert response.json()["data"] == {"phone": SHARMA_PHONE, "channel": "email", "expires_in": 120, "resend_after": 60}
    [otp] = outbox[SHARMA_EMAIL]
    assert len(otp) == 6 and otp.isdigit()
    assert otp not in response.text
    stored = redis.r.get(f"otp:{SHARMA_PHONE}")
    assert stored == hash_otp(SHARMA_PHONE, otp) and otp not in stored
    assert redis.r.ttl(f"otp:{SHARMA_PHONE}") == 120
    assert redis.r.exists(f"otp_attempts:{SHARMA_PHONE}") == 0


@pytest.mark.parametrize("phone", ["12345", "98765432101", "5876543210", "98765abcde", ""])
def test_invalid_phone_is_rejected(api, phone):
    assert error(send(api, phone)) == (422, "VALIDATION_ERROR")
    assert error(verify(api, phone, "123456")) == (422, "VALIDATION_ERROR")


def test_email_is_no_longer_accepted_for_otp(api):
    response = api.post("/api/v1/auth/send-otp", json={"email": "sharma.kirana@example.com"})
    assert error(response) == (422, "VALIDATION_ERROR")


@pytest.mark.parametrize("phone", [UNKNOWN_PHONE, DESK_PHONE, ADMIN_PHONE, "9000000003"])
def test_send_otp_response_is_identical_for_non_retailers_and_unknown_numbers(api, redis, outbox, phone):
    expected = send(api, SHARMA_PHONE).json()
    response = send(api, phone)
    assert response.status_code == 200
    assert response.json() == {**expected, "data": {**expected["data"], "phone": phone}}
    assert list(outbox) == [SHARMA_EMAIL]  # only the retailer's email got an OTP
    assert redis.r.exists(f"otp:{phone}") == 0


def test_send_otp_to_inactive_retailer_gives_generic_response_and_no_otp(api, tx, redis, outbox):
    seed_user(tx, "retailer_gupta").is_active = False
    tx.flush()
    response = send(api, GUPTA_PHONE)
    assert (response.status_code, response.json()["message"]) == (200, GENERIC_MESSAGE)
    assert GUPTA_EMAIL not in outbox and redis.r.exists(f"otp:{GUPTA_PHONE}") == 0


def test_otp_is_emailed_to_the_accounts_registered_address(api, outbox):
    send(api, GUPTA_PHONE)
    assert list(outbox) == [GUPTA_EMAIL]
    assert send(api, GUPTA_PHONE).status_code == 429  # same phone-based limits as before


def test_retailer_without_email_gets_503_and_no_otp_is_stored(api, tx, redis, outbox, caplog):
    seed_user(tx, "retailer_gupta").email = None
    tx.flush()
    assert error(send(api, GUPTA_PHONE)) == (503, "OTP_DELIVERY_FAILED")
    assert outbox == {} and redis.r.exists(f"otp:{GUPTA_PHONE}") == 0
    assert "no registered email address" in caplog.text


def test_otp_flow_logs_each_step_without_the_otp(api, outbox, caplog):
    with caplog.at_level("INFO"):
        send(api, SHARMA_PHONE)
        otp = outbox[SHARMA_EMAIL][0]
        token = verify(api, SHARMA_PHONE, otp).json()["data"]["access_token"]
    for step in ("[OTP] OTP generated", f"[OTP] Redis key: otp:{SHARMA_PHONE}", "[OTP] Redis SET operation started",
                 "[OTP] Redis SET operation successful", "[OTP] Redis check after SET: EXISTS=1 TTL=120s",
                 "[OTP] Email delivery successful via mock", "[OTP] Redis check after email: EXISTS=1",
                 "[OTP] OTP deleted from Redis: otp:9000000101 (reason: verified successfully)", "OTP login successful"):
        assert step in caplog.text
    assert otp not in caplog.text and token not in caplog.text
    assert hash_otp(SHARMA_PHONE, otp) not in caplog.text
    assert SHARMA_EMAIL not in caplog.text  # emails are masked in logs


# ---------------------------------------------------------------- send-otp rate limits


def test_resend_within_60_seconds_is_refused(api, redis):
    send(api, SHARMA_PHONE)
    response = send(api, SHARMA_PHONE)
    assert error(response) == (429, "RATE_LIMIT_EXCEEDED")
    assert response.json()["details"]["reason"] == "RESEND_COOLDOWN"
    assert 0 < response.json()["details"]["retry_after"] <= 60
    assert response.headers["Retry-After"] == str(response.json()["details"]["retry_after"])


def test_at_most_5_otp_requests_per_15_minutes(api, redis, outbox):
    for _ in range(5):
        assert send(api, SHARMA_PHONE).status_code == 200
        redis.end_cooldown(SHARMA_PHONE)
    response = send(api, SHARMA_PHONE)
    assert error(response) == (429, "RATE_LIMIT_EXCEEDED")
    assert response.json()["details"]["reason"] == "OTP_REQUEST_LIMIT"
    assert 0 < response.json()["details"]["retry_after"] <= 900
    assert redis.r.get(f"otp_requests:{SHARMA_PHONE}") == "5"
    assert len(outbox[SHARMA_EMAIL]) == 5  # the 6th request sent nothing


def test_rate_limits_apply_to_unknown_numbers_too(api, redis):
    """Otherwise a 429 would reveal that a number is registered."""
    send(api, UNKNOWN_PHONE)
    assert error(send(api, UNKNOWN_PHONE)) == (429, "RATE_LIMIT_EXCEEDED")


def test_resending_does_not_reset_the_request_limit(api, redis, outbox):
    send(api, SHARMA_PHONE)
    redis.end_cooldown(SHARMA_PHONE)
    send(api, SHARMA_PHONE)
    assert redis.r.get(f"otp_requests:{SHARMA_PHONE}") == "2"
    verify(api, SHARMA_PHONE, outbox[SHARMA_EMAIL][-1])
    assert redis.r.get(f"otp_requests:{SHARMA_PHONE}") == "2"


def test_concurrent_otp_requests_pass_the_cooldown_only_once(redis):
    store, results, barrier = AuthStore(redis), [], threading.Barrier(10)

    def request():
        barrier.wait()
        results.append(store.reserve_otp_request(SHARMA_PHONE, 60, 5, 900)[0])

    threads = [threading.Thread(target=request) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert (results.count(RateLimit.OK), results.count(RateLimit.COOLDOWN)) == (1, 9)


# ---------------------------------------------------------------- verify-otp


def test_correct_otp_logs_in_and_consumes_the_otp(api, redis, outbox):
    send(api, SHARMA_PHONE)
    response = verify(api, SHARMA_PHONE, outbox[SHARMA_EMAIL][0])
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["token_type"] == "bearer" and data["expires_in"] == 1800
    assert (data["user"]["role"], data["user"]["phone"]) == ("RETAILER", SHARMA_PHONE)
    assert data["user"]["retailer_id"] == str(seed_id("retailer", "sharma"))
    token = claims(data["access_token"])
    assert (token["sub"], token["role"]) == (str(seed_id("user", "retailer_sharma")), "RETAILER")
    assert token["exp"] - token["iat"] == 30 * 60
    assert redis.r.exists(f"otp:{SHARMA_PHONE}", f"otp_attempts:{SHARMA_PHONE}") == 0


def test_incorrect_otp_counts_attempts(api, redis, outbox):
    send(api, SHARMA_PHONE)
    response = verify(api, SHARMA_PHONE, wrong(outbox[SHARMA_EMAIL][0]))
    assert error(response) == (401, "INVALID_OTP")
    assert response.json()["details"] == {"remaining_attempts": 4}
    assert 0 < redis.r.ttl(f"otp_attempts:{SHARMA_PHONE}") <= 120  # expires with the OTP


def test_fifth_incorrect_attempt_locks_and_deletes_the_otp(api, redis, outbox):
    send(api, SHARMA_PHONE)
    otp = outbox[SHARMA_EMAIL][0]
    codes = [verify(api, SHARMA_PHONE, wrong(otp)).json() for _ in range(5)]
    assert [c["error_code"] for c in codes] == ["INVALID_OTP"] * 4 + ["OTP_ATTEMPTS_EXCEEDED"]
    assert [c["details"].get("remaining_attempts") for c in codes[:4]] == [4, 3, 2, 1]
    assert verify(api, SHARMA_PHONE, otp).json()["error_code"] == "OTP_EXPIRED"


def test_otp_expires(api, redis, outbox):
    send(api, SHARMA_PHONE)
    assert redis.r.ttl(f"otp:{SHARMA_PHONE}") == 120
    redis.r.pexpire(f"otp:{SHARMA_PHONE}", 1)  # fast-forward to the end of the 120 seconds
    time.sleep(0.01)
    assert error(verify(api, SHARMA_PHONE, outbox[SHARMA_EMAIL][0])) == (401, "OTP_EXPIRED")


def test_resend_invalidates_the_previous_otp_and_resets_its_attempts(api, redis, outbox):
    send(api, SHARMA_PHONE)
    first = outbox[SHARMA_EMAIL][0]
    verify(api, SHARMA_PHONE, wrong(first))
    redis.end_cooldown(SHARMA_PHONE)
    send(api, SHARMA_PHONE)
    second = outbox[SHARMA_EMAIL][1]
    assert redis.r.exists(f"otp_attempts:{SHARMA_PHONE}") == 0
    if first != second:
        assert verify(api, SHARMA_PHONE, first).json()["error_code"] == "INVALID_OTP"
    assert verify(api, SHARMA_PHONE, second).status_code == 200


def test_otp_cannot_be_reused(api, outbox):
    send(api, SHARMA_PHONE)
    otp = outbox[SHARMA_EMAIL][0]
    assert verify(api, SHARMA_PHONE, otp).status_code == 200
    assert verify(api, SHARMA_PHONE, otp).json()["error_code"] == "OTP_EXPIRED"


def test_otp_is_bound_to_its_phone(api, redis, outbox):
    send(api, SHARMA_PHONE)
    assert verify(api, GUPTA_PHONE, outbox[SHARMA_EMAIL][0]).json()["error_code"] == "OTP_EXPIRED"
    assert redis.r.exists(f"otp:{SHARMA_PHONE}") == 1
    assert hash_otp(SHARMA_PHONE, "123456") != hash_otp(GUPTA_PHONE, "123456")


def test_internal_users_cannot_log_in_with_otp(api, redis):
    AuthStore(redis).save_otp(DESK_PHONE, hash_otp(DESK_PHONE, "123456"), 120)
    assert error(verify(api, DESK_PHONE, "123456")) == (401, "UNAUTHORIZED")


def test_retailer_deactivated_after_otp_was_sent_cannot_log_in(api, tx, outbox):
    send(api, SHARMA_PHONE)
    seed_user(tx, "retailer_sharma").is_active = False
    tx.flush()
    assert error(verify(api, SHARMA_PHONE, outbox[SHARMA_EMAIL][0])) == (403, "ACCOUNT_DISABLED")


def test_concurrent_verifications_consume_an_otp_only_once(redis):
    store = AuthStore(redis)
    otp_hash = hash_otp(SHARMA_PHONE, "123456")
    store.save_otp(SHARMA_PHONE, otp_hash, 120)
    results, barrier = [], threading.Barrier(10)

    def attempt():
        barrier.wait()
        results.append(store.verify_otp(SHARMA_PHONE, otp_hash, 5)[0])

    threads = [threading.Thread(target=attempt) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert (results.count(OtpCheck.OK), results.count(OtpCheck.EXPIRED)) == (1, 9)


def test_concurrent_wrong_guesses_never_exceed_the_attempt_limit(redis):
    store = AuthStore(redis)
    store.save_otp(SHARMA_PHONE, hash_otp(SHARMA_PHONE, "123456"), 120)
    results, barrier = [], threading.Barrier(20)

    def attempt(i):
        barrier.wait()
        results.append(store.verify_otp(SHARMA_PHONE, hash_otp(SHARMA_PHONE, f"{i:06d}"), 5)[0])

    threads = [threading.Thread(target=attempt, args=(i + 1,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert (results.count(OtpCheck.INVALID), results.count(OtpCheck.LOCKED), results.count(OtpCheck.EXPIRED)) == (4, 1, 15)


# ---------------------------------------------------------------- Redis and email failures


def test_redis_failure_returns_503(tx_client, outbox, staff_password):
    app.dependency_overrides[get_auth_store] = lambda: AuthStore(BrokenUpstash())
    for response in (
        send(tx_client, SHARMA_PHONE),
        send(tx_client, UNKNOWN_PHONE),
        verify(tx_client, SHARMA_PHONE, "123456"),
        login(tx_client, DESK_PHONE),
    ):
        assert error(response) == (503, "AUTH_SERVICE_UNAVAILABLE")
    assert outbox == {}


def test_missing_upstash_configuration_returns_503(tx_client, monkeypatch):
    monkeypatch.setattr(auth_store_module.settings, "UPSTASH_REDIS_REST_URL", None)
    assert error(send(tx_client, SHARMA_PHONE)) == (503, "AUTH_SERVICE_UNAVAILABLE")
    assert send(tx_client, "12345").status_code == 422  # input errors still come first


def test_email_failure_removes_the_otp_and_returns_503(tx_client, redis, monkeypatch, caplog):
    app.dependency_overrides[get_auth_store] = lambda: AuthStore(redis)
    attempted = []

    async def fail(email, otp):
        attempted.append(otp)
        raise RuntimeError("mail server down")

    monkeypatch.setattr(auth_service, "send_otp_email", fail)
    response = send(tx_client, SHARMA_PHONE)
    assert error(response) == (503, "OTP_DELIVERY_FAILED")
    assert redis.r.exists(f"otp:{SHARMA_PHONE}", f"otp_attempts:{SHARMA_PHONE}") == 0
    assert "could not be sent" in caplog.text and attempted[0] not in caplog.text
    assert verify(tx_client, SHARMA_PHONE, attempted[0]).json()["error_code"] == "OTP_EXPIRED"


def test_mock_email_logs_otp_only_in_development(tx_client, redis, monkeypatch, caplog):
    app.dependency_overrides[get_auth_store] = lambda: AuthStore(redis)
    with caplog.at_level("WARNING", logger="dukaanflow.email"):
        assert send(tx_client, SHARMA_PHONE).status_code == 200
    assert f"[DEV MOCK EMAIL] OTP for {SHARMA_EMAIL} is" in caplog.text

    caplog.clear()
    redis.end_cooldown(SHARMA_PHONE)
    monkeypatch.setattr(mailer_module.settings, "ENVIRONMENT", "production")
    assert error(send(tx_client, SHARMA_PHONE)) == (503, "OTP_DELIVERY_FAILED")  # no mock fallback
    assert "[DEV MOCK EMAIL]" not in caplog.text
    assert redis.r.exists(f"otp:{SHARMA_PHONE}") == 0


# ---------------------------------------------------------------- password login


def test_password_login_returns_same_token_format_as_otp(api, outbox, staff_password):
    response = login(api, DESK_PHONE)
    assert response.status_code == 200
    data = response.json()["data"]
    assert (data["user"]["role"], data["token_type"], data["expires_in"]) == ("ORDER_DESK", "bearer", 1800)

    send(api, SHARMA_PHONE)
    otp_data = verify(api, SHARMA_PHONE, outbox[SHARMA_EMAIL][0]).json()["data"]
    assert set(claims(data["access_token"])) == set(claims(otp_data["access_token"])) == {"sub", "role", "iat", "exp"}
    assert set(data) == set(otp_data)


def test_passwords_are_stored_as_argon2id(tx, staff_password):
    stored = seed_user(tx, "order_desk").password_hash
    assert stored.startswith("$argon2id$") and PASSWORD not in stored


def test_wrong_password_unknown_phone_and_retailer_get_the_same_error(api, tx, staff_password):
    seed_user(tx, "retailer_sharma").password_hash = hash_password(PASSWORD)  # even with a password
    tx.flush()
    for phone, password in (
        (DESK_PHONE, "wrong password"),
        (UNKNOWN_PHONE, PASSWORD),
        (SHARMA_PHONE, PASSWORD),  # retailers sign in with OTP only
        ("9000000004", PASSWORD),  # salesman without a password
    ):
        response = login(api, phone, password)
        assert error(response) == (401, "INVALID_CREDENTIALS")
        assert response.json()["message"] == "Invalid phone number or password"


def test_inactive_user_cannot_log_in_with_password(api, tx, staff_password):
    seed_user(tx, "order_desk").is_active = False
    tx.flush()
    assert error(login(api, DESK_PHONE)) == (403, "ACCOUNT_DISABLED")


def test_login_is_limited_to_5_attempts_per_15_minutes(api, redis, staff_password):
    for _ in range(5):
        assert error(login(api, DESK_PHONE, "wrong password")) == (401, "INVALID_CREDENTIALS")
    response = login(api, DESK_PHONE)  # even the correct password is refused now
    assert error(response) == (429, "RATE_LIMIT_EXCEEDED")
    assert response.json()["details"]["reason"] == "LOGIN_ATTEMPTS"
    assert 0 < int(response.headers["Retry-After"]) <= 900
    assert 0 < redis.r.ttl(f"login_attempts:{DESK_PHONE}") <= 900


def test_successful_login_clears_failed_attempts(api, redis, staff_password):
    for _ in range(4):
        login(api, DESK_PHONE, "wrong password")
    assert login(api, DESK_PHONE).status_code == 200
    assert redis.r.exists(f"login_attempts:{DESK_PHONE}") == 0


def test_login_limit_applies_to_unknown_numbers_too(api):
    for _ in range(5):
        login(api, UNKNOWN_PHONE)
    assert error(login(api, UNKNOWN_PHONE)) == (429, "RATE_LIMIT_EXCEEDED")


def test_concurrent_login_attempts_never_exceed_the_limit(redis):
    store, results, barrier = AuthStore(redis), [], threading.Barrier(20)

    def attempt():
        barrier.wait()
        results.append(store.reserve_login_attempt(DESK_PHONE, 5, 900)[0])

    threads = [threading.Thread(target=attempt) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert (results.count(RateLimit.OK), results.count(RateLimit.LIMITED)) == (5, 15)


# ---------------------------------------------------------------- JWT and /auth/me


def me(client, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.get("/api/v1/auth/me", headers=headers)


def test_me_returns_the_authenticated_user(tx, tx_client):
    token, _ = create_access_token(seed_user(tx, "retailer_gupta"))
    data = me(tx_client, token).json()["data"]
    assert (data["phone"], data["role"], data["retailer_id"]) == (GUPTA_PHONE, "RETAILER", str(seed_id("retailer", "gupta")))


@pytest.mark.parametrize("token", [None, "not-a-jwt", "a.b.c"])
def test_missing_or_malformed_token_is_rejected(tx_client, token):
    assert error(me(tx_client, token)) == (401, "UNAUTHORIZED")


def test_token_with_wrong_signature_is_rejected(tx, tx_client):
    user = seed_user(tx, "admin")
    forged = jwt.encode({"sub": str(user.id), "role": "ADMIN", "exp": datetime.now(UTC) + timedelta(minutes=5)},
                        "some-other-secret-that-is-long-enough", algorithm="HS256")
    assert error(me(tx_client, forged)) == (401, "UNAUTHORIZED")


def test_expired_token_is_rejected(tx, tx_client):
    user = seed_user(tx, "admin")
    expired = jwt.encode({"sub": str(user.id), "role": "ADMIN", "exp": datetime.now(UTC) - timedelta(seconds=1)},
                         settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    assert error(me(tx_client, expired)) == (401, "TOKEN_EXPIRED")


def test_token_without_required_claims_is_rejected(tx_client):
    token = jwt.encode({"sub": str(uuid.uuid4())}, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    assert error(me(tx_client, token)) == (401, "UNAUTHORIZED")


def test_token_for_unknown_user_or_changed_role_is_rejected(tx, tx_client):
    ghost = User(id=uuid.uuid4(), name="Ghost", phone="9111111111", role="ADMIN")
    token, _ = create_access_token(ghost)
    assert me(tx_client, token).status_code == 401

    user = seed_user(tx, "salesman_sunil")
    token, _ = create_access_token(user)
    user.role = "ADMIN"  # role changed after the token was issued
    tx.flush()
    assert error(me(tx_client, token)) == (401, "UNAUTHORIZED")


def test_deactivated_user_loses_access_immediately(tx, tx_client):
    user = seed_user(tx, "retailer_sharma")
    token, _ = create_access_token(user)
    assert me(tx_client, token).status_code == 200
    user.is_active = False
    tx.flush()
    assert error(me(tx_client, token)) == (403, "ACCOUNT_DISABLED")


def test_production_refuses_default_jwt_secret():
    with pytest.raises(ValueError):
        Settings(_env_file=None, ENVIRONMENT="production")
    with pytest.raises(ValueError):
        Settings(_env_file=None, ENVIRONMENT="production", JWT_SECRET_KEY="short")


# ---------------------------------------------------------------- authorization


@pytest.fixture
def protected(tx):
    """A small app using the real dependencies, as future module routers will."""
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/order-desk-only")
    def order_desk_only(user: Annotated[User, Depends(require_roles(UserRole.ORDER_DESK, UserRole.ADMIN))]):
        return {"role": user.role}

    @test_app.get("/admin-only")
    def admin_only(user: Annotated[User, Depends(require_roles(UserRole.ADMIN))]):
        return {"role": user.role}

    @test_app.get("/retailers/{retailer_id}/credit")
    def credit(retailer_id: uuid.UUID, user: CurrentUser):
        summary = retailers_service.get_credit_summary(tx, user, retailer_id)
        return {"available": str(summary.available_credit)}

    def override_get_db():
        yield tx

    test_app.dependency_overrides[get_db] = override_get_db
    client = TestClient(test_app)

    def call(path, user_key=None):
        headers = {}
        if user_key:
            token, _ = create_access_token(seed_user(tx, user_key))
            headers["Authorization"] = f"Bearer {token}"
        return client.get(path, headers=headers).status_code

    return call


@pytest.mark.parametrize("user_key, expected", [
    ("order_desk", 200), ("admin", 200), ("salesman_sunil", 403), ("retailer_sharma", 403), (None, 401),
])
def test_role_based_access_to_order_desk_routes(protected, user_key, expected):
    assert protected("/order-desk-only", user_key) == expected


@pytest.mark.parametrize("user_key, expected", [("admin", 200), ("order_desk", 403)])
def test_admin_only_routes(protected, user_key, expected):
    assert protected("/admin-only", user_key) == expected


@pytest.mark.parametrize("user_key, retailer, expected", [
    ("retailer_sharma", "sharma", 200),   # own data
    ("retailer_sharma", "gupta", 403),    # another retailer's data
    ("salesman_sunil", "gupta", 200),     # assigned retailer
    ("salesman_sunil", "patel", 403),     # not assigned
    ("order_desk", "patel", 200),
])
def test_resource_ownership_through_the_token(protected, user_key, retailer, expected):
    assert protected(f"/retailers/{seed_id('retailer', retailer)}/credit", user_key) == expected
