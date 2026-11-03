from functools import lru_cache
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-jwt-secret-change-me"


class Settings(BaseSettings):
    """Application settings loaded from environment variables (and `.env` if present)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "DukaanFlow API"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    API_V1_PREFIX: str = "/api/v1"

    # Comma-separated list, e.g. "http://localhost:5173,http://127.0.0.1:5173"
    CORS_ORIGINS: str = "http://localhost:5173"

    # SQLAlchemy URL. Special characters in the password (e.g. "@") must be percent-encoded.
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/dukaanflow"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30  # seconds to wait for a free pooled connection
    DB_POOL_RECYCLE: int = 1800  # seconds before a pooled connection is replaced
    DB_CONNECT_TIMEOUT: int = 5  # seconds to wait when opening a new connection

    # Separate database used by the pytest suite (it is migrated and reseeded on every run).
    TEST_DATABASE_URL: str | None = None

    # Authentication (JWT access tokens; no refresh tokens in V1).
    JWT_SECRET_KEY: str = DEV_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Retailer OTP login (phone number in, OTP to the account's email). OTPs live only in
    # Upstash Redis (never in PostgreSQL).
    UPSTASH_REDIS_REST_URL: str | None = None
    UPSTASH_REDIS_REST_TOKEN: str | None = None
    OTP_EXPIRE_SECONDS: int = 120
    OTP_MAX_ATTEMPTS: int = 5  # incorrect verifications per OTP
    OTP_RESEND_COOLDOWN_SECONDS: int = 60  # per phone number
    OTP_MAX_REQUESTS: int = 5  # OTP requests per phone number per window
    OTP_REQUEST_WINDOW_SECONDS: int = 900  # 15 minutes
    LOGIN_MAX_ATTEMPTS: int = 5  # password attempts per phone number per window
    LOGIN_WINDOW_SECONDS: int = 900  # 15 minutes
    # OTP email delivery: "mock" logs the OTP (development only); "brevo" sends real email.
    EMAIL_PROVIDER: str = "mock"
    BREVO_API_KEY: str | None = None
    BREVO_SENDER_EMAIL: str | None = None  # a sender verified in Brevo
    BREVO_SENDER_NAME: str = "DukaanFlow"

    # Development only: if set, the seed gives internal demo users this password.
    DEMO_STAFF_PASSWORD: str | None = None

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() == "development"

    @model_validator(mode="after")
    def _check_security_settings(self) -> Self:
        if self.JWT_ALGORITHM not in ("HS256", "HS384", "HS512"):
            raise ValueError("JWT_ALGORITHM must be HS256, HS384 or HS512")
        if not self.is_development and (
            self.JWT_SECRET_KEY == DEV_JWT_SECRET or len(self.JWT_SECRET_KEY) < 32
        ):
            raise ValueError("Set a random JWT_SECRET_KEY of at least 32 characters outside development")
        if self.EMAIL_PROVIDER not in ("mock", "brevo"):
            raise ValueError("EMAIL_PROVIDER must be 'mock' or 'brevo'")
        if not self.is_development and self.EMAIL_PROVIDER == "mock":
            raise ValueError("EMAIL_PROVIDER=mock is only allowed when ENVIRONMENT=development")
        if self.EMAIL_PROVIDER == "brevo" and not (self.BREVO_API_KEY and self.BREVO_SENDER_EMAIL):
            raise ValueError("EMAIL_PROVIDER=brevo needs BREVO_API_KEY and BREVO_SENDER_EMAIL")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
