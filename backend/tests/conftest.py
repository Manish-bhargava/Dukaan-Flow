"""Shared fixtures. Database tests run against a separate test database
(TEST_DATABASE_URL, default: "<DATABASE_URL database>_test"), which is created if missing,
rebuilt with Alembic (downgrade base -> upgrade head) and seeded twice per test session.
They are skipped if PostgreSQL is not reachable.
"""

from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import get_db
from app.main import app
from seed.run_seed import run_seed, seed_id

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _test_database_url() -> str:
    if settings.TEST_DATABASE_URL:
        return settings.TEST_DATABASE_URL
    url = make_url(settings.DATABASE_URL)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def test_engine() -> Generator[Engine, None, None]:
    url = make_url(_test_database_url())
    server = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 3},
    )
    try:
        with server.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    except OperationalError as exc:
        pytest.skip(f"PostgreSQL is not reachable: {exc}")
    finally:
        server.dispose()

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.attributes["database_url"] = url.render_as_string(hide_password=False)
    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def seed_runs(test_engine: Engine) -> tuple[dict, dict]:
    """Run the seed twice against the fresh test database; return both summaries."""
    with Session(test_engine) as session:
        first = run_seed(session)
    with Session(test_engine) as session:
        second = run_seed(session)
    return first, second


@pytest.fixture
def db_session(test_engine: Engine, seed_runs) -> Generator[Session, None, None]:
    with Session(test_engine) as session:
        yield session
        session.rollback()


@pytest.fixture
def client(test_engine: Engine, seed_runs) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        with Session(test_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def tx(test_engine: Engine, seed_runs) -> Generator[Session, None, None]:
    """Session for workflow tests: service commits only release savepoints, and everything
    is rolled back when the test ends, so tests cannot affect each other."""
    connection = test_engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


def seed_user(session: Session, key: str):
    """Seeded users: admin, order_desk, salesman_sunil, salesman_deepak,
    retailer_sharma, retailer_gupta."""
    from app.models import User

    return session.get(User, seed_id("user", key))


@pytest.fixture
def tx_client(tx: Session) -> Generator[TestClient, None, None]:
    """API client whose requests use the `tx` session (sees uncommitted test data)."""

    def override_get_db() -> Generator[Session, None, None]:
        yield tx

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
