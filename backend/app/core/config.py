from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
