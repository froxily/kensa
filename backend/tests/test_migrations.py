import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session

from kensa.analytics.refresh import refresh_changed
from kensa.db.base import Base
from kensa.db.health import probe_database
from kensa.db.models import DEFAULT_WORKSPACE_ID
from kensa.history.fingerprints import backfill
from kensa.investigations.service import NewInvestigation, create_investigation
from tests.conftest import alembic_config as _alembic_config
from tests.history_helpers import populated_investigation

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


V1_0_HEAD = "0007_cause_status"  # the schema of the public v1.0.0 release


def _rows(engine: Engine) -> dict[str, list[str]]:
    """Every row of every table in the public schema, as sorted text (order-independent)."""
    with engine.connect() as conn:
        tables = sorted(t for t in inspect(conn).get_table_names() if t != "alembic_version")
        return {
            table: sorted(
                repr(tuple(row))
                for row in conn.execute(text(f'SELECT * FROM "{table}"')).all()  # noqa: S608
            )
            for table in tables
        }


def test_a_v1_0_database_upgrades_with_every_row_unchanged(test_database_url: str) -> None:
    """Upgrading a database written by v1.0 keeps every existing row exactly; the v1.1 features
    (fingerprint backfill, analytics) then work on that data."""
    config = _alembic_config(test_database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine(test_database_url)
    try:
        first = populated_investigation(
            engine, DEFAULT_WORKSPACE_ID, "acme", "upgrade", "KENSA_UPGRADE", run_id=71, job_id=72
        )
        with Session(engine) as session, session.begin():
            new = NewInvestigation("pasted", "paste", "mock", "job.log", "Error: boom\nexit 1\n")
            second = create_investigation(session, DEFAULT_WORKSPACE_ID, new, None).id
        command.downgrade(config, V1_0_HEAD)  # now a v1.0 database holding v1.0 data
        before = _rows(engine)
        for table in ("investigations", "chunks", "citations", "agent_events"):
            assert before[table], table
        assert "ci_runs" not in before
        assert "failure_fingerprints" not in before

        command.upgrade(config, "head")
        after = _rows(engine)
        for table, rows in before.items():
            assert after[table] == rows, table

        with Session(engine) as session, session.begin():
            done = backfill(session, DEFAULT_WORKSPACE_ID)
            refreshed = refresh_changed(session, DEFAULT_WORKSPACE_ID)
        assert set(done) == {first, second}
        assert refreshed >= 1
        with engine.connect() as conn:
            linked = conn.execute(text("SELECT count(*) FROM investigation_fingerprints")).scalar()
            daily = conn.execute(text("SELECT sum(investigations) FROM analytics_daily")).scalar()
        assert linked == 1  # the short pasted log names no failure line
        assert daily == 2
    finally:
        engine.dispose()
        command.upgrade(config, "head")
