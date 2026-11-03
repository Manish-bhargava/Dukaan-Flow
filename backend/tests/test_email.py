"""Brevo email provider for OTPs. Brevo is never called: httpx.MockTransport stands in for
the API, and Upstash is replaced by fakeredis (real Lua)."""

import asyncio
import json

import httpx
import pytest

from app.core.config import Settings
from app.core.security import hash_otp
from app.main import app
from app.modules.auth import mailer
from app.modules.auth.auth_store import AuthStore, get_auth_store
from app.modules.auth.mailer import BREVO_API_URL, EmailDeliveryError
from tests.test_auth import GENERIC_MESSAGE, SHARMA_EMAIL, SHARMA_PHONE, UNKNOWN_PHONE, FakeUpstash

API_KEY, SENDER = "xkeysib-test-key-123", "login@dukaanflow.test"


class BrevoFake:
    """Records requests and answers like the Brevo transactional email API."""

    def __init__(self, status=201, body=None, error: Exception | None = None, raw: bytes | None = None):
        self.requests: list[httpx.Request] = []
        self.status, self.body, self.error, self.raw = status, body, error, raw

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.error:
            raise self.error
        if self.raw is not None:
            return httpx.Response(self.status, content=self.raw)
        return httpx.Response(self.status, json=self.body if self.body is not None else {"messageId": "<202611040001.abc@smtp-relay.mailin.fr>"})

    def sent(self, index=0) -> dict:
        return json.loads(self.requests[index].content)


@pytest.fixture
def brevo(monkeypatch):
    """Selects Brevo email with a fake API behind it; returns an installer."""
    monkeypatch.setattr(mailer.settings, "EMAIL_PROVIDER", "brevo")
    monkeypatch.setattr(mailer.settings, "BREVO_API_KEY", API_KEY)
    monkeypatch.setattr(mailer.settings, "BREVO_SENDER_EMAIL", SENDER)
    state = {"fake": BrevoFake()}
    monkeypatch.setattr(mailer, "_http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(state["fake"])))

    def install(fake: BrevoFake) -> BrevoFake:
        state["fake"] = fake
        return fake

    return install


@pytest.fixture
def api(tx_client):
    redis = FakeUpstash()
    app.dependency_overrides[get_auth_store] = lambda: AuthStore(redis)
    tx_client.redis = redis
    return tx_client


def send_directly(otp="482913"):
    return asyncio.run(mailer.send_otp_email(SHARMA_EMAIL, otp))


def sent_otp(fake: BrevoFake) -> str:
    return fake.sent()["textContent"].split("verification code is: ")[1][:6]


# ---------------------------------------------------------------- provider


def test_brevo_email_request_matches_the_tested_integration(brevo):
    fake = brevo(BrevoFake())
    assert send_directly()["messageId"]
    [request] = fake.requests
    assert (request.method, str(request.url)) == ("POST", BREVO_API_URL)
    assert request.headers["api-key"] == API_KEY
    assert request.headers["accept"] == "application/json"
    assert request.headers["content-type"] == "application/json"
    body = fake.sent()
    assert body["sender"] == {"name": "DukaanFlow", "email": SENDER}
    assert body["to"] == [{"email": SHARMA_EMAIL}]
    assert body["subject"] == "Your DukaanFlow Login OTP"
    assert body["textContent"] == (
        "Hello,\n\nYour DukaanFlow verification code is: 482913\n\n"
        "This OTP is valid for 2 minutes.\nDo not share this code with anyone.\n\n"
        "Regards,\nDukaanFlow Team"
    )
    html = body["htmlContent"]
    assert "DukaanFlow" in html and "482913" in html and "2 minutes" in html and "Do not share" in html


@pytest.mark.parametrize("fake, reason", [
    (BrevoFake(401, {"code": "unauthorized", "message": "Key not found"}), "invalid API key"),
    (BrevoFake(403, {"code": "permission_denied", "message": "unauthorized IP"}), "unauthorized IP"),
    (BrevoFake(400, {"code": "invalid_parameter", "message": "sender is invalid / inactive"}), "sender is invalid"),
    (BrevoFake(502, raw=b"<html>Bad gateway</html>"), "HTTP 502"),
    (BrevoFake(error=httpx.ReadTimeout("timed out")), "timed out"),
    (BrevoFake(error=httpx.ConnectError("no route")), "ConnectError"),
])
def test_brevo_failures_raise_without_leaking_secrets(brevo, fake, reason):
    brevo(fake)
    with pytest.raises(EmailDeliveryError) as exc:
        send_directly()
    assert reason in str(exc.value)
    assert "482913" not in str(exc.value) and API_KEY not in str(exc.value)


def test_missing_sender_fails_before_any_request(brevo, monkeypatch):
    fake = brevo(BrevoFake())
    monkeypatch.setattr(mailer.settings, "BREVO_SENDER_EMAIL", None)
    with pytest.raises(EmailDeliveryError):
        send_directly()
    assert fake.requests == []


def test_mock_provider_sends_nothing(brevo, monkeypatch):
    fake = brevo(BrevoFake())
    monkeypatch.setattr(mailer.settings, "EMAIL_PROVIDER", "mock")
    assert send_directly() is None and fake.requests == []


# ---------------------------------------------------------------- send-otp with Brevo


def test_send_otp_emails_the_registered_address_and_logs_in(api, brevo, caplog):
    fake = brevo(BrevoFake())
    response = api.post("/api/v1/auth/send-otp", json={"phone": SHARMA_PHONE})
    assert (response.status_code, response.json()["message"]) == (200, GENERIC_MESSAGE)
    assert response.json()["data"]["channel"] == "email"
    assert fake.sent()["to"] == [{"email": SHARMA_EMAIL}]
    otp = sent_otp(fake)
    assert otp not in response.text and otp not in caplog.text and API_KEY not in caplog.text
    assert api.redis.r.get(f"otp:{SHARMA_PHONE}") == hash_otp(SHARMA_PHONE, otp)
    assert api.redis.r.ttl(f"otp:{SHARMA_PHONE}") == 120
    verified = api.post("/api/v1/auth/verify-otp", json={"phone": SHARMA_PHONE, "otp": otp})
    assert verified.status_code == 200 and verified.json()["data"]["access_token"]


@pytest.mark.parametrize("fake", [
    BrevoFake(401, {"code": "unauthorized", "message": "Key not found"}),
    BrevoFake(error=httpx.ReadTimeout("timed out")),
])
def test_brevo_failure_returns_503_and_leaves_no_usable_otp(api, brevo, caplog, fake):
    brevo(fake)
    response = api.post("/api/v1/auth/send-otp", json={"phone": SHARMA_PHONE})
    assert (response.status_code, response.json()["error_code"]) == (503, "OTP_DELIVERY_FAILED")
    assert api.redis.r.exists(f"otp:{SHARMA_PHONE}", f"otp_attempts:{SHARMA_PHONE}") == 0
    otp = sent_otp(fake)
    assert otp not in response.text and otp not in caplog.text and API_KEY not in caplog.text
    assert api.post("/api/v1/auth/verify-otp", json={"phone": SHARMA_PHONE, "otp": otp}).json()["error_code"] == "OTP_EXPIRED"


def test_failed_delivery_still_counts_toward_rate_limits(api, brevo):
    brevo(BrevoFake(error=httpx.ConnectError("down")))
    api.post("/api/v1/auth/send-otp", json={"phone": SHARMA_PHONE})
    again = api.post("/api/v1/auth/send-otp", json={"phone": SHARMA_PHONE})
    assert again.json()["details"]["reason"] == "RESEND_COOLDOWN"


def test_no_email_is_sent_for_unknown_numbers(api, brevo):
    fake = brevo(BrevoFake())
    response = api.post("/api/v1/auth/send-otp", json={"phone": UNKNOWN_PHONE})
    assert (response.status_code, response.json()["message"]) == (200, GENERIC_MESSAGE)
    assert fake.requests == []


# ---------------------------------------------------------------- configuration


def test_email_configuration_is_checked_at_startup():
    secret = "s" * 48
    with pytest.raises(ValueError, match="mock is only allowed"):
        Settings(_env_file=None, ENVIRONMENT="production", JWT_SECRET_KEY=secret, EMAIL_PROVIDER="mock")
    with pytest.raises(ValueError, match="BREVO_API_KEY and BREVO_SENDER_EMAIL"):
        Settings(_env_file=None, EMAIL_PROVIDER="brevo", BREVO_API_KEY="k")
    with pytest.raises(ValueError, match="must be 'mock' or 'brevo'"):
        Settings(_env_file=None, EMAIL_PROVIDER="sms")
    ok = Settings(_env_file=None, ENVIRONMENT="production", JWT_SECRET_KEY=secret, EMAIL_PROVIDER="brevo",
                  BREVO_API_KEY="k", BREVO_SENDER_EMAIL="login@example.com")
    assert ok.EMAIL_PROVIDER == "brevo"
