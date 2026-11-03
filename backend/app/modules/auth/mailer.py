"""OTP delivery by email through Brevo, ported from the tested standalone email_service.py
(same endpoint, headers, payload and httpx.AsyncClient request).

The auth service calls `await send_otp_email(email, otp)`. On any failure
EmailDeliveryError is raised; the service then deletes the stored OTP and returns 503
OTP_DELIVERY_FAILED. Brevo's 201 means the email was accepted, not that it reached the inbox.

EMAIL_PROVIDER=mock (development only; config.py refuses it elsewhere) logs the OTP instead
of sending. The API key is never logged; only the mock logs the OTP.
"""

import logging
from html import escape
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("dukaanflow.email")

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"
OTP_SUBJECT = "Your DukaanFlow Login OTP"


class EmailDeliveryError(Exception):
    """The email was not accepted. The message never contains the OTP or the API key."""


def mask_email(email: str) -> str:
    """For logs: s****@example.com."""
    local, _, domain = email.partition("@")
    return f"{local[:1]}****@{domain}"


def otp_text(otp: str) -> str:
    # Same wording as the tested email_service.py.
    return (
        "Hello,\n\n"
        f"Your DukaanFlow verification code is: {otp}\n\n"
        "This OTP is valid for 2 minutes.\n"
        "Do not share this code with anyone.\n\n"
        "Regards,\n"
        "DukaanFlow Team"
    )


def otp_html(otp: str) -> str:
    code = escape(otp)
    return (
        '<div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;color:#1f2937">'
        '<h2 style="color:#047857;margin-bottom:4px">DukaanFlow</h2>'
        "<p>Hello,</p>"
        "<p>Your DukaanFlow verification code is:</p>"
        f'<p style="font-size:28px;font-weight:bold;letter-spacing:6px">{code}</p>'
        "<p>This OTP is valid for <strong>2 minutes</strong>.</p>"
        "<p><strong>Do not share this code with anyone.</strong> DukaanFlow will never ask for it.</p>"
        "<p>Regards,<br>DukaanFlow Team</p></div>"
    )


def _http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=20)


async def send_email(to_email: str, subject: str, text: str, html: str | None = None) -> dict[str, Any]:
    if not settings.BREVO_API_KEY or not settings.BREVO_SENDER_EMAIL:
        raise EmailDeliveryError("BREVO_API_KEY or BREVO_SENDER_EMAIL is not set")

    payload: dict[str, Any] = {
        "sender": {"name": settings.BREVO_SENDER_NAME, "email": settings.BREVO_SENDER_EMAIL},
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": text,
    }
    if html:
        payload["htmlContent"] = html
    headers = {
        "api-key": settings.BREVO_API_KEY,
        "accept": "application/json",
        "content-type": "application/json",
    }
    try:
        async with _http_client() as client:
            response = await client.post(BREVO_API_URL, json=payload, headers=headers)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        hint = {
            401: "invalid API key",
            403: "check transactional email activation, API key permissions, sender and IP authorization",
        }.get(status, "")
        raise EmailDeliveryError(
            f"Brevo rejected the email: HTTP {status} {exc.response.text[:300]} {hint}".strip()
        ) from None
    except httpx.TimeoutException:
        raise EmailDeliveryError("Brevo request timed out") from None
    except httpx.HTTPError as exc:
        raise EmailDeliveryError(f"Network error while connecting to Brevo: {type(exc).__name__}") from None

    result = response.json() if response.content else {}
    logger.info(
        "Brevo accepted email to %s: HTTP %s, messageId=%s",
        mask_email(to_email), response.status_code, result.get("messageId"),
    )
    return result


async def send_otp_email(email: str, otp: str) -> dict[str, Any] | None:
    if settings.EMAIL_PROVIDER == "mock":
        if not settings.is_development:
            raise EmailDeliveryError(
                f"EMAIL_PROVIDER=mock is not allowed when ENVIRONMENT={settings.ENVIRONMENT}"
            )
        logger.warning("[DEV MOCK EMAIL] OTP for %s is %s (valid %s seconds)", email, otp, settings.OTP_EXPIRE_SECONDS)
        return None
    return await send_email(email, OTP_SUBJECT, otp_text(otp), otp_html(otp))
