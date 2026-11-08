"""Alembic environment. The URL comes from Kensa settings, or from
``config.attributes["database_url"]`` when migrations are run programmatically (tests)."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from kensa.core.config import get_settings
from kensa.db import models  # noqa: F401  (registers models on Base.metadata)
from kensa.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    override = config.attributes.get("database_url")
    if override:
        return str(override)
    return get_settings().database_url.get_secret_value()


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Fail fast (instead of hanging) when the database container is not running.
    connectable = create_engine(
        _database_url(), poolclass=pool.NullPool, connect_args={"connect_timeout": 5}
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
