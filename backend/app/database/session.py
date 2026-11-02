from collections.abc import Generator

from sqlalchemy.orm import Session, sessionmaker

from app.database.connection import engine

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session for a single request and always close it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
