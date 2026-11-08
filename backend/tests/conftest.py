"""Shared fixtures. DB tests run against a separate ``kensa_test`` database and are skipped,
with an explicit reason, when the local PostgreSQL is not running."""

import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from kensa.core.config import Settings
from kensa.db.models import DEFAULT_WORKSPACE_ID

# Tests never write trace files; test_telemetry.py installs its own in-memory exporter.
os.environ.setdefault("KENSA_TELEMETRY_ENABLED", "false")
# Starlette's TestClient sends "Host: testserver".
os.environ.setdefault("KENSA_ALLOWED_HOSTS", '["127.0.0.1", "localhost", "testserver"]')

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DB_NAME = "kensa_test"
_TABLES = (
    "jobs, agent_events, citations, diagnoses, evidence, error_signatures, chunks, documents, "
    "investigations, repositories"
)
_CHECKPOINT_TABLES = (
    "langgraph.checkpoints, langgraph.checkpoint_blobs, langgraph.checkpoint_writes"
)


def alembic_config(url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.attributes["database_url"] = url
    return config


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = make_url(Settings().database_url.get_secret_value())
    admin_dsn = url.set(drivername="postgresql", database="postgres").render_as_string(
        hide_password=False
    )
    try:
        with psycopg.connect(admin_dsn, autocommit=True, connect_timeout=3) as conn:
            exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB_NAME,)
            ).fetchone()
            if exists is None:
                conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(TEST_DB_NAME)))
    except psycopg.OperationalError:
        pytest.skip("local PostgreSQL not reachable: run `docker compose up -d db`")
    return url.set(database=TEST_DB_NAME).render_as_string(hide_password=False)


@pytest.fixture
def db_engine(test_database_url: str) -> Iterator[Engine]:
    """A migrated, emptied test database (only the default workspace remains)."""
    command.upgrade(alembic_config(test_database_url), "head")
    engine = create_engine(test_database_url, pool_size=12, max_overflow=4)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE"))
        conn.execute(text(f"TRUNCATE {_CHECKPOINT_TABLES}"))
        conn.execute(
            text("DELETE FROM workspaces WHERE id <> :default"), {"default": DEFAULT_WORKSPACE_ID}
        )
    yield engine
    engine.dispose()
