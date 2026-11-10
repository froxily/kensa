"""Backend for Playwright end-to-end tests.

Uses a dedicated ``kensa_e2e`` database on the local Compose PostgreSQL (created and migrated
on start, emptied on every run), the deterministic mock provider and a fast-polling worker.
Listens on 127.0.0.1 only. Started by ``frontend/playwright.config.ts``; not for development.

    uv run --directory backend --no-sync python ../scripts/e2e_server.py
"""

from pathlib import Path

import psycopg
import uvicorn
from alembic import command
from alembic.config import Config
from psycopg import sql
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from kensa.app import create_app
from kensa.core.config import Settings

E2E_DB = "kensa_e2e"
PORT = 8010
BACKEND = Path(__file__).resolve().parents[1] / "backend"
TRUNCATE = text(
    "TRUNCATE jobs, agent_events, citations, diagnoses, evidence, error_signatures, chunks, "
    "documents, investigations, langgraph.checkpoints, langgraph.checkpoint_blobs, "
    "langgraph.checkpoint_writes, failure_fingerprints, tracked_repositories, analytics_daily, "
    "analytics_watermarks, purge_audits, dq_findings RESTART IDENTITY CASCADE"
)


def prepare_database(base: Settings, name: str = E2E_DB) -> str:
    """Create (if needed), migrate and empty a dedicated database; return its URL."""
    url = make_url(base.database_url.get_secret_value())
    admin = url.set(drivername="postgresql", database="postgres")
    with psycopg.connect(admin.render_as_string(hide_password=False), autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
        if exists.fetchone() is None:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    e2e_url = url.set(database=name).render_as_string(hide_password=False)

    config = Config()
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.attributes["database_url"] = e2e_url
    command.upgrade(config, "head")
    engine = create_engine(e2e_url)
    with engine.begin() as conn:
        conn.execute(TRUNCATE)
    engine.dispose()
    return e2e_url


def main() -> None:
    base = Settings()
    settings = base.model_copy(
        update={
            "database_url": SecretStr(prepare_database(base)),
            "inference_provider": "mock",
            "embedding_provider": "mock",
            "worker_enabled": True,
            "worker_poll_seconds": 0.2,
        }
    )
    uvicorn.run(create_app(settings), host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
