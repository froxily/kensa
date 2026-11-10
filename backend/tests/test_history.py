"""v1.1 CI history (D-052): parsing caps, the incremental sync, data quality, Forget repository
and retention, the history API, and the history worker. GitHub is always faked (no network)."""

import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from kensa.app import create_app
from kensa.core.config import Settings
from kensa.db.models import (
    DEFAULT_WORKSPACE_ID,
    CiJob,
    CiRun,
    Citation,
    Diagnosis,
    DqFinding,
    EtlBatch,
    Investigation,
    Job,
    PurgeAudit,
    TrackedRepository,
    Workspace,
)
from kensa.github.client import SHARED_CACHE, GitHubError
from kensa.history.github import (
    BudgetExhaustedError,
    RepositoryMeta,
    RequestBudget,
    job_record,
    run_record,
)
from kensa.history.purge import (
    PURGE_COVERAGE,
    REMOVED_QUOTE,
    apply_retention,
    digest,
    forget_repository,
)
from kensa.history.quality import CHECKS, run_checks
from kensa.history.service import enqueue_sync, make_history_handler, track_repository
from kensa.history.sync import SYNC_JOB, iso, sync_repository
from kensa.investigations.service import INVESTIGATE_JOB
from kensa.jobs import queue
from kensa.jobs.worker import Worker
from tests.github_fixtures import API, OWNER, REPO
from tests.history_helpers import (
    NOW,
    FakeClient,
    job_json,
    marker_locations,
    populated_investigation,
    reader,
    run_json,
    sha,
)

WS = DEFAULT_WORKSPACE_ID


# ---------------------------------------------------------------- parsing (no database) ---


def test_run_records_cap_strings_and_never_keep_the_actor() -> None:
    data = run_json(5, path="x" * 900)
    record = run_record(data)
    assert len(record.workflow_path) == 300
    assert record.head_sha == sha(5)
    assert not hasattr(record, "actor")
    with pytest.raises(GitHubError):
        run_record({**data, "head_sha": "not-a-sha"})


def test_job_records_cap_steps_and_labels() -> None:
    data = job_json(1, 5)
    data["steps"] = [{"number": n, "name": "s" * 500} for n in range(300)]
    data["labels"] = [f"label-{n}" for n in range(50)]
    record = job_record(data)
    assert len(record.steps) == 100
    assert len(record.steps[0].name) == 200
    assert len(record.labels) == 20


def test_the_budget_stops_at_its_limit() -> None:
    budget = RequestBudget(2)
    budget.spend()
    budget.spend()
    with pytest.raises(BudgetExhaustedError):
        budget.spend()


def test_the_reader_only_asks_github_for_repository_paths() -> None:
    client = FakeClient()
    client.runs = [run_json(1)]
    runs, total = reader(client).runs_page(OWNER, REPO, created="2026-11-01..2026-11-09", page=1)
    assert total == 1
    assert runs[0].run_id == 1
    assert all(path.startswith(f"/repos/{OWNER}/{REPO}/") for path in client.calls)


# ---------------------------------------------------------------------- sync (database) ---


def _tracked(engine: Engine, owner: str = OWNER, repo: str = REPO) -> uuid.UUID:
    with Session(engine) as session, session.begin():
        tracked, _ = track_repository(
            session, WS, RepositoryMeta(owner, repo, "main", private=False), 30
        )
        return tracked.id


def _count(engine: Engine, model: Any) -> int:
    with Session(engine) as session:
        return int(session.execute(select(func.count()).select_from(model)).scalar_one())


@pytest.mark.db
def test_a_sync_loads_runs_and_failed_jobs_and_a_repeat_changes_nothing(db_engine: Engine) -> None:
    tracked = _tracked(db_engine)
    client = FakeClient()
    client.runs = [
        run_json(1, conclusion="failure"),
        run_json(2),
        run_json(3, status="in_progress"),
    ]
    client.jobs[(1, 1)] = [job_json(11, 1), job_json(12, 1, conclusion="success")]

    first = sync_repository(
        db_engine, reader(client), workspace_id=WS, tracked_repository_id=tracked, now=NOW
    )
    assert first.status == "succeeded"
    assert first.counts["runs_inserted"] == 3
    assert first.counts["jobs_inserted"] == 2
    assert _count(db_engine, CiRun) == 3
    assert _count(db_engine, CiJob) == 2
    with Session(db_engine) as session:
        state = session.get(TrackedRepository, tracked).sync_state  # type: ignore[union-attr]
    assert state["complete_through"] == iso(NOW)
    assert state["pending"] == [[3, 1]]

    # The in-progress run finished: the pending re-read records the change once.
    finished = run_json(3)
    client.runs[2] = finished
    second = sync_repository(
        db_engine, reader(client), workspace_id=WS, tracked_repository_id=tracked, now=NOW
    )
    assert second.counts["runs_changed"] == 1
    assert second.counts["runs_inserted"] == 0

    third = sync_repository(
        db_engine, reader(client), workspace_id=WS, tracked_repository_id=tracked, now=NOW
    )
    assert third.status == "succeeded"
    assert third.counts["runs_inserted"] == third.counts["runs_changed"] == 0
    assert third.counts["jobs_inserted"] == third.counts["jobs_changed"] == 0
    assert _count(db_engine, CiRun) == 3
    assert _count(db_engine, CiJob) == 2
    with Session(db_engine) as session:
        batches = session.execute(select(func.count()).select_from(EtlBatch)).scalar_one()
    assert batches == 3


@pytest.mark.db
def test_a_rerun_reads_its_earlier_attempts(db_engine: Engine) -> None:
    tracked = _tracked(db_engine)
    client = FakeClient()
    client.runs = [run_json(5, attempt=2)]
    client.attempts[(5, 1)] = run_json(5, attempt=1, conclusion="failure")
    client.jobs[(5, 1)] = [job_json(51, 5)]
    outcome = sync_repository(
        db_engine, reader(client), workspace_id=WS, tracked_repository_id=tracked, now=NOW
    )
    assert outcome.counts["attempts_read"] == 1
    with Session(db_engine) as session:
        attempts = session.execute(
            select(CiRun.run_attempt, CiRun.conclusion).order_by(CiRun.run_attempt)
        ).all()
    assert [tuple(a) for a in attempts] == [(1, "failure"), (2, "success")]
    assert _count(db_engine, CiJob) == 1


@pytest.mark.db
def test_an_exhausted_budget_keeps_the_cursor_and_the_next_sync_continues(
    db_engine: Engine,
) -> None:
    tracked = _tracked(db_engine)
    client = FakeClient()
    client.runs = [run_json(1000 + n) for n in range(150)]
    partial = sync_repository(
        db_engine,
        reader(client, budget=1),
        workspace_id=WS,
        tracked_repository_id=tracked,
        now=NOW,
    )
    assert partial.status == "partial"
    assert _count(db_engine, CiRun) == 100
    with Session(db_engine) as session:
        state = session.get(TrackedRepository, tracked).sync_state  # type: ignore[union-attr]
    assert state["window"]["next_page"] == 2
    assert state.get("complete_through") is None

    done = sync_repository(
        db_engine,
        reader(client, budget=10),
        workspace_id=WS,
        tracked_repository_id=tracked,
        now=NOW + timedelta(hours=1),
    )
    assert done.status == "succeeded"
    assert _count(db_engine, CiRun) == 150
    with Session(db_engine) as session:
        state = session.get(TrackedRepository, tracked).sync_state  # type: ignore[union-attr]
    # The window that was interrupted completes at its own end, not at the later sync's time.
    assert state["complete_through"] == iso(NOW)
    assert state["window"] is None


@pytest.mark.db
def test_a_rate_limit_ends_the_sync_without_rescheduling(db_engine: Engine) -> None:
    tracked = _tracked(db_engine)
    client = FakeClient()
    client.fail_with = GitHubError("rate_limited", "Try again after 13:00 UTC.", 429)
    outcome = sync_repository(
        db_engine, reader(client), workspace_id=WS, tracked_repository_id=tracked, now=NOW
    )
    assert outcome.status == "rate_limited"
    assert outcome.error_code == "rate_limited"
    with Session(db_engine) as session:
        batch = session.get(EtlBatch, outcome.batch_id)
        assert batch is not None
        assert batch.status == "rate_limited"
        assert session.execute(select(func.count()).select_from(Job)).scalar_one() == 0


@pytest.mark.db
def test_a_private_repository_is_never_stored(db_engine: Engine) -> None:
    tracked = _tracked(db_engine)
    client = FakeClient()
    client.runs = [run_json(1, private=True)]
    outcome = sync_repository(
        db_engine, reader(client), workspace_id=WS, tracked_repository_id=tracked, now=NOW
    )
    assert outcome.status == "failed"
    assert outcome.error_code == "private_repository"
    assert _count(db_engine, CiRun) == 0
    with Session(db_engine) as session, pytest.raises(GitHubError):
        track_repository(session, WS, RepositoryMeta("o", "r", "main", private=True), 30)


# ------------------------------------------------------------------------- data quality ---


def _investigation(session: Session, rule: str | None = None) -> uuid.UUID:
    investigation = Investigation(
        workspace_id=WS, title="t", source="paste", provider="mock", rule_category=rule
    )
    session.add(investigation)
    session.flush()
    return investigation.id


@pytest.mark.db
def test_quality_checks_find_every_seeded_defect_and_resolve_fixed_ones(db_engine: Engine) -> None:
    tracked = _tracked(db_engine)
    client = FakeClient()
    client.runs = [run_json(1, conclusion="failure"), run_json(2), run_json(3)]
    client.jobs[(1, 1)] = []  # a failed run whose jobs come back empty
    sync_repository(db_engine, reader(client), workspace_id=WS, tracked_repository_id=tracked)
    owner, repo = OWNER, REPO
    with Session(db_engine) as session, session.begin():
        session.execute(text("UPDATE ci_runs SET run_started_at = NULL WHERE run_id = 2"))
        run3 = session.execute(select(CiRun.id).where(CiRun.run_id == 3)).scalar_one()
        session.add_all(
            [
                CiJob(
                    workspace_id=WS,
                    ci_run_id=run3,
                    job_id=31,
                    name="a",
                    status="completed",
                    conclusion="success",
                    started_at=NOW,
                    completed_at=NOW - timedelta(1),
                ),
                CiJob(
                    workspace_id=WS,
                    ci_run_id=run3,
                    job_id=32,
                    name="b",
                    status="completed",
                    conclusion="success",
                    started_at=NOW,
                    completed_at=None,
                ),
            ]
        )
        for _ in range(2):  # the same job imported twice (before v1.1's de-duplication)
            iid = _investigation(session)
            session.execute(
                text(
                    "INSERT INTO workflow_runs (id, workspace_id, investigation_id, owner, repo, "
                    "run_id, run_number, run_attempt, workflow_name, workflow_path, event, "
                    "head_sha, html_url, job_id, job_name, job_html_url, log_source) VALUES "
                    "(gen_random_uuid(), :ws, :iid, :o, :r, 77, 1, 1, 'ci', 'ci.yml', 'push', "
                    ":sha, 'u', 770, 'test', 'u', 'github')"
                ),
                {"ws": WS, "iid": iid, "o": owner, "r": repo, "sha": sha(77)},
            )
        disagreeing = _investigation(session, rule="docker")
        session.add(
            Diagnosis(
                workspace_id=WS,
                investigation_id=disagreeing,
                category="db_connectivity",
                summary="s",
                root_cause="r",
                confidence=0.3,
                uncertainty="",
                recommended_fixes=[],
                verification_status="plausible",
                verification_notes=[],
                provider="mock",
            )
        )
        batch = session.execute(select(EtlBatch).limit(1)).scalar_one()
        batch.counts = {**batch.counts, "listing_truncated": 1}

    with Session(db_engine) as session, session.begin():
        found = run_checks(session, WS)
    # Every check fires on its seeded defect (the fingerprint check has its own test).
    seeded = {check.name for check in CHECKS} - {"fingerprint_category_conflict"}
    assert seeded == {name for name, n in found.items() if n > 0}

    with Session(db_engine) as session, session.begin():
        session.execute(text("UPDATE ci_runs SET run_started_at = now() WHERE run_id = 2"))
    with Session(db_engine) as session, session.begin():
        again = run_checks(session, WS)
    assert again["run_missing_timestamps"] == 0
    with Session(db_engine) as session:
        rows = session.execute(
            select(DqFinding.resolved_at).where(DqFinding.check == "run_missing_timestamps")
        ).all()
        assert len(rows) == 1
        assert rows[0].resolved_at is not None
        total = session.execute(select(func.count()).select_from(DqFinding)).scalar_one()
    assert total == len(seeded)  # one finding per seeded defect, and no duplicates


# --------------------------------------------------------------------------------- purge ---


@pytest.mark.db
def test_every_workspace_table_has_a_purge_rule(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        tables = set(
            conn.execute(
                text(
                    "SELECT table_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND column_name = 'workspace_id'"
                )
            ).scalars()
        )
    assert tables == set(PURGE_COVERAGE)


@pytest.mark.db
def test_forget_repository_leaves_nothing_that_could_rebuild_its_evidence(
    db_engine: Engine,
) -> None:
    forgotten, kept = "FORGET_ME_7f3a", "KEEP_ME_91bc"
    gone = populated_investigation(db_engine, WS, "acme", "vault", forgotten, run_id=1, job_id=10)
    other = populated_investigation(db_engine, WS, "acme", "other", kept, run_id=2, job_id=20)
    tracked = _tracked(db_engine, "acme", "vault")
    client = FakeClient()
    client.runs = [run_json(1, conclusion="failure")]
    client.jobs[(1, 1)] = [job_json(10, 1)]
    sync_repository(db_engine, reader(client), workspace_id=WS, tracked_repository_id=tracked)
    with Session(db_engine) as session, session.begin():
        # The other investigation once cited the forgotten one's incident document.
        incident_chunk = session.execute(
            text(
                "SELECT c.id FROM chunks c JOIN documents d ON d.id = c.document_id "
                "WHERE d.name = :n"
            ),
            {"n": f"incident/{gone}"},
        ).scalar_one()
        diagnosis = session.execute(
            select(Diagnosis.id).where(Diagnosis.investigation_id == other)
        ).scalar_one()
        session.add(
            Citation(
                workspace_id=WS,
                diagnosis_id=diagnosis,
                ordinal=2,
                evidence_label="E9",
                line_number=2,
                chunk_id=incident_chunk,
                quote=f"{forgotten} again",
                valid=True,
            )
        )
        run_checks(session, WS)
    assert marker_locations(db_engine, forgotten)  # it is really there before

    with Session(db_engine) as session, session.begin():
        counts = forget_repository(session, WS, "ACME", "Vault")  # names are case-insensitive

    assert marker_locations(db_engine, forgotten) == []
    assert counts["investigations"] == 1
    assert counts["tracked_repositories"] == 1
    assert counts["langgraph_checkpoints"] == 1
    assert counts["incident_documents"] == 1
    assert counts["quotes_scrubbed"] >= 1
    assert marker_locations(db_engine, kept)  # the other repository is untouched
    with Session(db_engine) as session:
        assert session.get(Investigation, gone) is None
        assert session.get(Investigation, other) is not None
        quotes = session.execute(select(Citation.quote).where(Citation.diagnosis_id == diagnosis))
        assert REMOVED_QUOTE in set(quotes.scalars())
        audit = session.execute(select(PurgeAudit)).scalar_one()
        assert audit.scope_digest == digest("acme/vault")
        assert "vault" not in str(audit.counts)
        assert session.execute(select(func.count()).select_from(CiRun)).scalar_one() == 0


@pytest.mark.db
def test_retention_deletes_whole_investigations_not_just_their_logs(db_engine: Engine) -> None:
    old_marker = "OLD_RUN_c41d"
    old = populated_investigation(db_engine, WS, "acme", "app", old_marker, run_id=3, job_id=30)
    recent = populated_investigation(
        db_engine, WS, "acme", "app", "RECENT_e20f", run_id=4, job_id=40
    )
    with Session(db_engine) as session, session.begin():
        session.execute(
            text(
                "UPDATE investigations SET created_at = now() - interval '100 days' WHERE id = :i"
            ),
            {"i": old},
        )
        counts = apply_retention(session, WS, 90)
    assert counts["investigations"] == 1
    assert marker_locations(db_engine, old_marker) == []
    with Session(db_engine) as session:
        assert session.get(Investigation, recent) is not None
    with Session(db_engine) as session, pytest.raises(ValueError, match="at least one day"):
        apply_retention(session, WS, 0)


# ----------------------------------------------------------------------------------- API ---


class Api:
    def __init__(self, client: TestClient, engine: Engine, settings: Settings) -> None:
        self.client, self.engine, self.settings = client, engine, settings


@pytest.fixture
def api(db_engine: Engine, test_database_url: str) -> Iterator[Api]:
    settings = Settings(
        _env_file=None,
        database_url=test_database_url,
        worker_enabled=False,
        inference_provider="mock",
        embedding_provider="mock",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        yield Api(client, app.state.engine, settings)


@pytest.fixture
def github() -> Iterator[respx.MockRouter]:
    SHARED_CACHE._items.clear()
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        router.route(host="testserver").pass_through()
        yield router


def _mock_repository(github: respx.MockRouter, private: bool = False) -> None:
    github.get(f"{API}/repos/{OWNER}/{REPO}").mock(
        return_value=httpx.Response(200, json={"default_branch": "main", "private": private})
    )


@pytest.mark.db
def test_track_sync_and_forget_through_the_api(api: Api, github: respx.MockRouter) -> None:
    _mock_repository(github)
    url = f"https://github.com/{OWNER}/{REPO}"
    created = api.client.post("/api/history/repositories", json={"url": url})
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["owner"], body["repo"], body["runs"], body["syncing"]) == (OWNER, REPO, 0, False)
    again = api.client.post("/api/history/repositories", json={"url": url})
    assert again.json()["id"] == body["id"]

    run_url = f"{url}/actions/runs/123"
    assert api.client.post("/api/history/repositories", json={"url": run_url}).status_code == 422

    first = api.client.post(f"/api/history/repositories/{body['id']}/sync", json={})
    second = api.client.post(f"/api/history/repositories/{body['id']}/sync", json={})
    assert first.status_code == 202
    assert first.json()["created"] is True
    assert second.json() == {"job_id": first.json()["job_id"], "created": False}
    assert api.client.get("/api/history/repositories").json()[0]["syncing"] is True

    wrong = api.client.post(
        f"/api/history/repositories/{body['id']}/forget", json={"confirm": "someone/else"}
    )
    assert wrong.status_code == 422
    done = api.client.post(
        f"/api/history/repositories/{body['id']}/forget", json={"confirm": f"{OWNER}/{REPO}"}
    )
    assert done.status_code == 200
    assert done.json()["counts"]["tracked_repositories"] == 1
    assert api.client.get("/api/history/repositories").json() == []
    assert _count(api.engine, Job) == 0  # its queued sync went with it


@pytest.mark.db
def test_a_private_repository_cannot_be_tracked(api: Api, github: respx.MockRouter) -> None:
    _mock_repository(github, private=True)
    response = api.client.post(
        "/api/history/repositories", json={"url": f"https://github.com/{OWNER}/{REPO}"}
    )
    assert response.status_code == 422
    assert _count(api.engine, TrackedRepository) == 0


@pytest.mark.db
def test_another_workspaces_repository_is_not_found(api: Api) -> None:
    with Session(api.engine) as session, session.begin():
        other = Workspace(name=f"other-{uuid.uuid4().hex[:6]}")
        session.add(other)
        session.flush()
        foreign = TrackedRepository(workspace_id=other.id, owner="x", repo="y")
        session.add(foreign)
        session.flush()
        foreign_id, other_id = foreign.id, other.id
    base = f"/api/history/repositories/{foreign_id}"
    assert api.client.post(f"{base}/sync", json={}).status_code == 404
    assert api.client.get(f"{base}/batches").status_code == 404
    assert api.client.post(f"{base}/forget", json={"confirm": "x/y"}).status_code == 404
    assert api.client.get("/api/history/repositories").json() == []
    with Session(api.engine) as session, session.begin():
        session.execute(text("DELETE FROM workspaces WHERE id = :i"), {"i": other_id})


@pytest.mark.db
def test_retention_needs_explicit_confirmation(api: Api) -> None:
    refused = api.client.post("/api/history/retention", json={"older_than_days": 30})
    assert refused.status_code == 422
    done = api.client.post("/api/history/retention", json={"older_than_days": 30, "confirm": True})
    assert done.status_code == 200


# -------------------------------------------------------------------------------- worker ---


@pytest.mark.db
def test_the_history_worker_syncs_and_checks_quality(api: Api) -> None:
    tracked = _tracked(api.engine)
    client = FakeClient()
    client.runs = [run_json(1, conclusion="failure"), run_json(2)]
    client.jobs[(1, 1)] = [job_json(11, 1)]
    with Session(api.engine) as session, session.begin():
        enqueue_sync(session, WS, tracked)
    handler = make_history_handler(api.settings, client_factory=lambda _: client)  # type: ignore[arg-type,return-value]
    assert Worker(api.engine, {SYNC_JOB: handler}, only_handled=True).run_once()
    with Session(api.engine) as session:
        job = session.execute(select(Job)).scalar_one()
        batch = session.execute(select(EtlBatch)).scalar_one()
    assert job.status == "succeeded"
    assert batch.status == "succeeded"
    assert batch.counts["runs_inserted"] == 2


@pytest.mark.db
def test_workers_only_claim_their_own_kinds(db_engine: Engine) -> None:
    tracked = _tracked(db_engine)
    with Session(db_engine) as session, session.begin():
        iid = _investigation(session)
        queue.enqueue(
            session,
            workspace_id=WS,
            kind=INVESTIGATE_JOB,
            idempotency_key=f"investigate:{iid}:1",
            investigation_id=iid,
        )
    history_worker = Worker(db_engine, {SYNC_JOB: lambda lease, engine: None}, only_handled=True)
    assert history_worker.run_once() is False  # the investigation is not its job
    with Session(db_engine) as session, session.begin():
        enqueue_sync(session, WS, tracked)
    assert history_worker.run_once() is True
    with Session(db_engine) as session:
        kinds = dict(session.execute(select(Job.kind, Job.status)).all())
    assert kinds == {INVESTIGATE_JOB: "queued", SYNC_JOB: "succeeded"}

    # The agent worker leaves syncs to the history worker.
    with Session(db_engine) as session, session.begin():
        session.execute(text("DELETE FROM jobs WHERE kind = :k"), {"k": INVESTIGATE_JOB})
        enqueue_sync(session, WS, tracked)
    agent_worker = Worker(
        db_engine, {INVESTIGATE_JOB: lambda lease, engine: None}, exclude=(SYNC_JOB,)
    )
    assert agent_worker.run_once() is False
    assert history_worker.run_once() is True


@pytest.mark.db
def test_malformed_and_duplicated_records_never_stop_or_double_a_sync(db_engine: Engine) -> None:
    """A run GitHub sends without an id or a creation time is skipped and counted; pagination
    still continues after a full page that held one; a run listed twice is stored once."""
    tracked = _tracked(db_engine)
    client = FakeClient()
    good = [run_json(n, created=NOW - timedelta(minutes=n)) for n in range(1, 100)]
    broken = run_json(500)
    del broken["created_at"]
    client.runs = [*good[:50], broken, *good[50:], run_json(200), run_json(2)]  # 2 twice
    outcome = sync_repository(
        db_engine, reader(client), workspace_id=WS, tracked_repository_id=tracked, now=NOW
    )
    assert outcome.status == "succeeded"
    assert outcome.counts["malformed_skipped"] == 1
    assert _count(db_engine, CiRun) == 100  # 99 good runs and run 200 on the second page
    with Session(db_engine) as session:
        state = session.get(TrackedRepository, tracked).sync_state  # type: ignore[union-attr]
    assert state["complete_through"] == iso(NOW)


@pytest.mark.db
def test_a_window_over_githubs_listing_limit_is_split_never_marked_complete_early(
    db_engine: Engine,
) -> None:
    """GitHub lists at most 1,000 runs per query, newest first. The older runs of a busy window
    must still be read before the window counts as complete (review finding)."""
    tracked = _tracked(db_engine)
    client = FakeClient()
    client.runs = [run_json(n, created=NOW - timedelta(minutes=n)) for n in range(1, 1051)]
    outcome = sync_repository(
        db_engine,
        reader(client, budget=400),
        workspace_id=WS,
        tracked_repository_id=tracked,
        now=NOW,
    )
    assert outcome.status == "succeeded"
    assert outcome.counts["windows_split"] >= 1
    assert outcome.counts["listing_truncated"] == 0
    assert _count(db_engine, CiRun) == 1050
    with Session(db_engine) as session:
        state = session.get(TrackedRepository, tracked).sync_state  # type: ignore[union-attr]
    assert state["complete_through"] == iso(NOW)


@pytest.mark.db
def test_an_interrupted_earlier_attempt_gets_its_jobs_on_the_next_sync(db_engine: Engine) -> None:
    tracked = _tracked(db_engine)
    client = FakeClient()
    rerun = run_json(7, attempt=2)
    client.runs = [rerun]
    client.attempts[(7, 1)] = run_json(7, attempt=1, conclusion="failure")
    client.jobs[(7, 1)] = [job_json(71, 7)]
    # Enough budget for the listing and the earlier attempt, not for its jobs.
    first = sync_repository(
        db_engine,
        reader(client, budget=2),
        workspace_id=WS,
        tracked_repository_id=tracked,
        now=NOW,
    )
    assert first.status == "partial"
    assert _count(db_engine, CiJob) == 0
    second = sync_repository(
        db_engine, reader(client), workspace_id=WS, tracked_repository_id=tracked, now=NOW
    )
    assert second.status == "succeeded"
    assert _count(db_engine, CiJob) == 1


@pytest.mark.db
def test_every_pending_run_is_rechecked_within_a_bounded_number_of_syncs(
    db_engine: Engine,
) -> None:
    from kensa.history.sync import MAX_PENDING

    tracked = _tracked(db_engine)
    client = FakeClient()
    count = MAX_PENDING + 5
    client.runs = [
        run_json(n, status="in_progress", created=NOW - timedelta(days=5, minutes=n))
        for n in range(1, count + 1)
    ]
    sync_repository(
        db_engine,
        reader(client),
        workspace_id=WS,
        tracked_repository_id=tracked,
        now=NOW - timedelta(days=4),
    )
    # They all finish; the listing window has moved on, so only the pending queue sees them.
    client.runs = [
        run_json(n, created=NOW - timedelta(days=5, minutes=n)) for n in range(1, count + 1)
    ]
    for _ in range(2):
        sync_repository(
            db_engine, reader(client), workspace_id=WS, tracked_repository_id=tracked, now=NOW
        )
    with Session(db_engine) as session:
        state = session.get(TrackedRepository, tracked).sync_state  # type: ignore[union-attr]
        unfinished = session.execute(
            select(func.count()).select_from(CiRun).where(CiRun.status != "completed")
        ).scalar_one()
    assert state["pending"] == []
    assert unfinished == 0
