import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# Indian mobile number: 10 digits starting with 6-9 (no country code).
Phone = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[6-9]\d{9}$")]


class SendOtpInput(BaseModel):
    phone: Phone


class VerifyOtpInput(BaseModel):
    phone: Phone
    otp: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\d{6}$")]


class PasswordLoginInput(BaseModel):
    phone: Phone
    password: str = Field(min_length=1, max_length=128)


class OtpRequestOut(BaseModel):
    phone: str
    channel: str = "email"  # where the OTP is delivered
    expires_in: int  # OTP validity in seconds
    resend_after: int  # seconds before another OTP can be requested


class AuthUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    phone: str
    email: str | None
    role: str
    retailer_id: uuid.UUID | None
    is_active: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthUserOut
