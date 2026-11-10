"""v1.1 analytics (D-055): an idempotent, incremental daily aggregate; origins kept apart; the
dashboard endpoint; workspace isolation; Forget repository removes the repository's rows."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Literal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from kensa.analytics.queries import Filters, summary
from kensa.analytics.refresh import ALL_ORIGINS, refresh_changed
from kensa.app import create_app
from kensa.core.config import Settings
from kensa.db.models import DEFAULT_WORKSPACE_ID, AnalyticsDaily, Investigation, Workspace
from kensa.history.github import RepositoryMeta
from kensa.history.purge import forget_repository
from kensa.history.service import track_repository
from kensa.history.sync import sync_repository
from kensa.investigations.service import NewInvestigation, create_investigation
from tests.history_helpers import FakeClient, job_json, reader, run_json

pytestmark = pytest.mark.db
WS = DEFAULT_WORKSPACE_ID
NOW = datetime.now(UTC).replace(microsecond=0)
LOG = "\n".join(
    [
        "2026-11-09T08:00:01.0000000Z src/settings.py:3: in <module>",
        "2026-11-09T08:00:01.1000000Z E   KeyError: 'BRAMBLE_TOKEN_URL'",
        "2026-11-09T08:00:02.0000000Z ##[error]Process completed with exit code 1.",
    ]
)


def _investigation(
    engine: Engine, source: Literal["paste", "sample"] = "paste", finished: bool = True
) -> uuid.UUID:
    with Session(engine) as session, session.begin():
        new = NewInvestigation(
            title="t", source=source, provider="mock", document_name="job.log", log_text=LOG
        )
        investigation = create_investigation(session, WS, new, None)
        if finished:
            investigation.status = "completed"
            investigation.finished_at = investigation.created_at + timedelta(seconds=12)
        return investigation.id


def _history(engine: Engine, owner: str = "acme", repo: str = "shop") -> None:
    with Session(engine) as session, session.begin():
        tracked, _ = track_repository(session, WS, RepositoryMeta(owner, repo, "main", False), 30)
        tracked_id = tracked.id
    client = FakeClient()
    client.runs = [
        run_json(1, conclusion="failure", created=NOW - timedelta(hours=1)),
        run_json(2, created=NOW - timedelta(hours=2)),
        run_json(3, created=NOW - timedelta(days=1, hours=1)),
    ]
    client.jobs[(1, 1)] = [job_json(11, 1)]
    sync_repository(engine, reader(client), workspace_id=WS, tracked_repository_id=tracked_id)


def _rows(engine: Engine) -> list[tuple[object, ...]]:
    with Session(engine) as session:
        return [
            tuple(r)
            for r in session.execute(
                select(
                    AnalyticsDaily.day,
                    AnalyticsDaily.source,
                    AnalyticsDaily.repository,
                    AnalyticsDaily.data_origin,
                    AnalyticsDaily.runs,
                    AnalyticsDaily.failed_runs,
                    AnalyticsDaily.investigations,
                ).order_by(AnalyticsDaily.day, AnalyticsDaily.source, AnalyticsDaily.data_origin)
            )
        ]


def test_the_refresh_is_idempotent_and_incremental(db_engine: Engine) -> None:
    _history(db_engine)
    _investigation(db_engine)
    _investigation(db_engine, source="sample")
    with Session(db_engine) as session, session.begin():
        first = refresh_changed(session, WS)
    before = _rows(db_engine)
    with Session(db_engine) as session, session.begin():
        again = refresh_changed(session, WS, extra=[NOW.date()])
    assert _rows(db_engine) == before  # recomputing a day gives the same rows
    assert first >= 1
    assert again == 1
    ci = [r for r in before if r[1] == "ci"]
    assert sum(int(r[4]) for r in ci) == 3  # type: ignore[call-overload]
    assert sum(int(r[5]) for r in ci) == 1  # type: ignore[call-overload]

    with Session(db_engine) as session, session.begin():
        nothing_new = refresh_changed(session, WS)
    assert nothing_new == 0
    _investigation(db_engine)
    with Session(db_engine) as session, session.begin():
        assert refresh_changed(session, WS) == 1  # only today's day is recomputed


def test_samples_and_fixtures_are_kept_apart_from_real_observations(db_engine: Engine) -> None:
    _investigation(db_engine)
    _investigation(db_engine, source="sample")
    with Session(db_engine) as session, session.begin():
        refresh_changed(session, WS)
    with Session(db_engine) as session:
        real = summary(session, WS, Filters.last_days(7))
        everything = summary(session, WS, Filters.last_days(7, origins=ALL_ORIGINS))
    assert real["investigations"] == 1
    assert everything["investigations"] == 2
    assert real["latency_p50_seconds"] == 12.0


# ------------------------------------------------------------------------------ API ---


@pytest.fixture
def client(db_engine: Engine, test_database_url: str) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        database_url=test_database_url,
        worker_enabled=False,
        inference_provider="mock",
        embedding_provider="mock",
        history_matching=True,  # experimental, off by default (D-057)
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def default_client(db_engine: Engine, test_database_url: str) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        database_url=test_database_url,
        worker_enabled=False,
        inference_provider="mock",
        embedding_provider="mock",
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_the_dashboard_answers_with_filters(client: TestClient, db_engine: Engine) -> None:
    _history(db_engine)
    _investigation(db_engine)
    _investigation(db_engine)
    body = client.get("/api/analytics/dashboard", params={"days": 7}).json()
    assert body["summary"]["runs"] == 3
    assert body["summary"]["failed_runs"] == 1
    assert body["summary"]["investigations"] == 2
    assert body["summary"]["recurring_failures"] == 1  # the same failure, twice
    assert len(body["trends"]) == 7
    assert body["recurring"][0]["occurrences"] == 2
    assert body["options"]["repositories"] == ["acme/shop"]
    assert body["freshness"][0]["repository"] == "acme/shop"
    only_repo = client.get(
        "/api/analytics/dashboard", params={"days": 7, "repository": "acme/shop"}
    ).json()
    assert only_repo["summary"]["runs"] == 3
    assert only_repo["summary"]["investigations"] == 0  # pasted logs belong to no repository
    assert client.get("/api/analytics/dashboard", params={"days": 0}).status_code == 422


def test_another_workspaces_analytics_are_invisible(client: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session, session.begin():
        other = Workspace(name=f"other-{uuid.uuid4().hex[:6]}")
        session.add(other)
        session.flush()
        session.add(
            Investigation(workspace_id=other.id, title="x", source="paste", provider="mock")
        )
        other_id = other.id
    body = client.get("/api/analytics/dashboard", params={"days": 7}).json()
    assert body["summary"]["investigations"] == 0
    with Session(db_engine) as session, session.begin():
        session.execute(text("DELETE FROM workspaces WHERE id = :i"), {"i": other_id})


def test_forget_repository_removes_its_analytics(db_engine: Engine) -> None:
    _history(db_engine)
    with Session(db_engine) as session, session.begin():
        refresh_changed(session, WS)
    with Session(db_engine) as session, session.begin():
        counts = forget_repository(session, WS, "acme", "shop")
    assert counts["analytics_rows"] >= 1
    with Session(db_engine) as session:
        left = session.execute(
            select(func.count())
            .select_from(AnalyticsDaily)
            .where(AnalyticsDaily.repository == "acme/shop")
        ).scalar_one()
    assert left == 0


def test_percentiles_are_computed_over_all_investigations_never_averaged(
    db_engine: Engine,
) -> None:
    """p50/p95 over several days come from the individual investigations, not from averaging
    each day's percentile (which would be wrong)."""
    durations = [10, 20, 30, 40, 1000]  # seconds; one slow outlier
    with Session(db_engine) as session, session.begin():
        for day, seconds in enumerate(durations):
            new = NewInvestigation(
                title="t", source="paste", provider="mock", document_name="job.log", log_text=LOG
            )
            investigation = create_investigation(session, WS, new, None)
            created = NOW - timedelta(days=day)
            investigation.created_at = created
            investigation.status = "completed"
            investigation.finished_at = created + timedelta(seconds=seconds)
    with Session(db_engine) as session, session.begin():
        refresh_changed(session, WS)
        result = summary(session, WS, Filters.last_days(30))
    assert result["investigations"] == 5
    assert result["latency_p50_seconds"] == 30.0
    # PostgreSQL's percentile_cont interpolates: 40 + 0.8 * (1000 - 40).
    assert result["latency_p95_seconds"] == 808.0


def test_an_unfinished_run_is_not_counted_until_it_has_an_outcome(db_engine: Engine) -> None:
    with Session(db_engine) as session, session.begin():
        tracked, _ = track_repository(session, WS, RepositoryMeta("acme", "wip", "main", False), 30)
        tracked_id = tracked.id
    client = FakeClient()
    client.runs = [
        run_json(41, conclusion="failure", created=NOW - timedelta(hours=1)),
        run_json(42, status="in_progress", created=NOW - timedelta(hours=1)),
    ]
    client.jobs[(41, 1)] = [job_json(141, 41)]
    sync_repository(db_engine, reader(client), workspace_id=WS, tracked_repository_id=tracked_id)
    with Session(db_engine) as session, session.begin():
        refresh_changed(session, WS, extra=[NOW.date(), (NOW - timedelta(hours=1)).date()])
        result = summary(session, WS, Filters.last_days(7))
    assert result["runs"] == 1
    assert result["failed_runs"] == 1
    assert result["failure_rate"] == 1.0


def test_concurrent_refreshes_of_one_day_never_collide(db_engine: Engine) -> None:
    """Two refreshes of an empty day at the same time (a dashboard request and a sync) both
    delete nothing and insert the same key; the per-workspace lock serialises them."""
    import threading

    _investigation(db_engine)
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def refresh() -> None:
        try:
            with Session(db_engine) as session, session.begin():
                barrier.wait()
                from kensa.analytics.refresh import refresh_days

                refresh_days(session, WS, [NOW.date()])
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=refresh) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert errors == []
    assert sum(int(r[6]) for r in _rows(db_engine) if r[1] == "investigation") == 1  # type: ignore[call-overload]


def test_recurring_failures_are_hidden_while_history_matching_is_off(
    default_client: TestClient, db_engine: Engine
) -> None:
    _investigation(db_engine)
    _investigation(db_engine)
    body = default_client.get("/api/analytics/dashboard", params={"days": 7}).json()
    assert body["history_matching"] is False
    assert body["summary"]["recurring_failures"] is None
    assert body["recurring"] == []
    assert body["summary"]["investigations"] == 2
