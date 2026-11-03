from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.core.config import settings
from app.database.base import Base

config = context.config

if config.config_file_name is not None:
    # Keep loggers that already exist (e.g. the app's, when migrations run inside the tests).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# The URL comes from app settings (DATABASE_URL). Callers such as the test suite can
# target a different database by setting config.attributes["database_url"].
database_url = config.attributes.get("database_url") or settings.DATABASE_URL


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of executing it (`alembic upgrade head --sql`)."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(database_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, compare_type=True
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
