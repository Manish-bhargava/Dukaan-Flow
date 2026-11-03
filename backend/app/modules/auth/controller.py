from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import User
from app.modules.auth import service
from app.modules.auth.auth_store import AuthStore
from app.modules.auth.schemas import (
    AuthUserOut,
    OtpRequestOut,
    PasswordLoginInput,
    SendOtpInput,
    VerifyOtpInput,
)
from app.utils.responses import success_response


def send_otp(db: Session, store: AuthStore, data: SendOtpInput) -> dict:
    service.request_otp(db, store, data.phone)
    return success_response(
        service.OTP_REQUEST_MESSAGE,
        OtpRequestOut(
            phone=data.phone,
            expires_in=settings.OTP_EXPIRE_SECONDS,
            resend_after=settings.OTP_RESEND_COOLDOWN_SECONDS,
        ),
    )


def verify_otp(db: Session, store: AuthStore, data: VerifyOtpInput) -> dict:
    return success_response("Login successful", service.verify_otp(db, store, data.phone, data.otp))


def login(db: Session, store: AuthStore, data: PasswordLoginInput) -> dict:
    return success_response(
        "Login successful", service.login_with_password(db, store, data.phone, data.password)
    )


def me(user: User) -> dict:
    return success_response("Profile fetched successfully", AuthUserOut.model_validate(user))
