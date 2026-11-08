"""Engine construction. Synchronous psycopg 3: its async mode cannot run on Windows'
default Proactor event loop, so DB work runs in FastAPI's threadpool (DECISIONS.md D-015)."""

from sqlalchemy import Engine, create_engine

from kensa.core.config import Settings


def build_engine(settings: Settings) -> Engine:
    # create_engine does not connect; the first checkout does.
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={"connect_timeout": 3},
    )
