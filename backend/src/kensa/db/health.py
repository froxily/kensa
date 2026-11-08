"""Database readiness probe used by ``/api/health``."""

from typing import Literal

import structlog
from pydantic import BaseModel
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

logger = structlog.get_logger(__name__)


class DatabaseStatus(BaseModel):
    status: Literal["ok", "unavailable"]
    pgvector_version: str | None = None
    detail: str | None = None


def probe_database(engine: Engine) -> DatabaseStatus:
    try:
        with engine.connect() as conn:
            version = conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            ).scalar_one_or_none()
    except SQLAlchemyError as exc:
        # Never log the exception text: driver messages can include connection details.
        logger.warning("database_probe_failed", error_type=type(exc).__name__)
        return DatabaseStatus(status="unavailable", detail="connection_failed")
    if version is None:
        return DatabaseStatus(status="ok", detail="pgvector_extension_missing")
    return DatabaseStatus(status="ok", pgvector_version=str(version))
