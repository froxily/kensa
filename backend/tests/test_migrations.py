import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from kensa.db.base import Base
from kensa.db.health import probe_database
from kensa.db.models import DEFAULT_WORKSPACE_ID
from tests.conftest import alembic_config as _alembic_config

pytestmark = pytest.mark.db


def test_upgrade_downgrade_roundtrip(test_database_url: str) -> None:
    config = _alembic_config(test_database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    engine = create_engine(test_database_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT id, name FROM workspaces")).all()
            assert [(row.id, row.name) for row in rows] == [(DEFAULT_WORKSPACE_ID, "default")]
        status = probe_database(engine)
        assert status.status == "ok"
        assert status.pgvector_version is not None

        command.downgrade(config, "base")
        assert "workspaces" not in inspect(engine).get_table_names()

        # Re-applying from scratch must work (reproducible history).
        command.upgrade(config, "head")
        assert {"workspaces", "investigations", "chunks", "jobs"} <= set(
            inspect(engine).get_table_names()
        )
    finally:
        engine.dispose()


def test_models_match_migrations(test_database_url: str) -> None:
    """The ORM models and the migration history must describe the same schema."""
    command.upgrade(_alembic_config(test_database_url), "head")
    engine = create_engine(test_database_url)
    try:
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert diff == []
    finally:
        engine.dispose()
