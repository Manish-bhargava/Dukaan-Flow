from sqlalchemy import create_engine

from app.core.config import settings

# The engine connects lazily: no connection is opened until a session is first used.
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,  # transparently replace connections dropped by the server
    connect_args={"connect_timeout": settings.DB_CONNECT_TIMEOUT},
)
