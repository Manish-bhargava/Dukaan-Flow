from sqlalchemy import create_engine

from app.core.config import settings

# The engine connects lazily: no connection is opened until a session is first used.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=False,
)
