from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.dependencies import CurrentUser, DbSession
from app.modules.auth import controller
from app.modules.auth.auth_store import AuthStore, get_auth_store
from app.modules.auth.schemas import (
    AuthUserOut,
    OtpRequestOut,
    PasswordLoginInput,
    SendOtpInput,
    TokenOut,
    VerifyOtpInput,
)
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/auth", tags=["auth"])

AuthStoreDep = Annotated[AuthStore, Depends(get_auth_store)]


@router.post("/send-otp", response_model=ApiResponse[OtpRequestOut])
def send_otp(data: SendOtpInput, db: DbSession, store: AuthStoreDep):
    return controller.send_otp(db, store, data)


@router.post("/verify-otp", response_model=ApiResponse[TokenOut])
def verify_otp(data: VerifyOtpInput, db: DbSession, store: AuthStoreDep):
    return controller.verify_otp(db, store, data)


@router.post("/login", response_model=ApiResponse[TokenOut])
def login(data: PasswordLoginInput, db: DbSession, store: AuthStoreDep):
    return controller.login(db, store, data)


@router.get("/me", response_model=ApiResponse[AuthUserOut])
def me(user: CurrentUser):
    return controller.me(user)
