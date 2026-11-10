"""Incremental, idempotent history sync (v1.1, D-052).

One sync reads a tracked repository's workflow runs created since the last complete window,
plus the jobs of failed run attempts, and upserts them by GitHub's own ids:

* **Idempotent:** an upsert changes a row only when a value differs, so syncing the same data
  again changes nothing (and reports zero changes).
* **Incremental:** ``sync_state.complete_through`` marks the end of the last complete window.
  The next window starts one day earlier (runs can be re-run or finish late), and runs that were
  still in progress are re-read until they complete.
* **Bounded:** a request budget per sync. When it runs out, everything stored so far is kept and
  the listing cursor stays on its page, so the next sync continues there.
* **Resumable:** every run is committed as it is loaded, after the job lease is checked.
* **Manual:** a sync runs when the operator asks for one. A rate limit or an exhausted budget ends
  the sync with a status saying when to try again; nothing is rescheduled automatically.
"""

import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import Boolean, Engine, literal_column, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import Label

from kensa.db.models import CiJob, CiRun, EtlBatch, TrackedRepository
from kensa.github.client import GitHubError
from kensa.history.github import (
    FAILED_CONCLUSIONS,
    MAX_LIST_PAGES,
    PER_PAGE,
    BudgetExhaustedError,
    HistoryReader,
    JobRecord,
    RunRecord,
)

logger = structlog.get_logger(__name__)

SYNC_JOB = "history_sync"
OVERLAP = timedelta(days=1)
MAX_PENDING = 20

Fence = Callable[[Session], None]


def _no_fence(_: Session) -> None:
    return None


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class SyncOutcome:
    batch_id: uuid.UUID
    status: str
    counts: Counter[str] = field(default_factory=Counter)
    requests_used: int = 0
    error_code: str | None = None
    message: str | None = None


# ------------------------------------------------------------------------------- upserts ---

# PostgreSQL leaves xmax at 0 on a freshly inserted row: tells an insert from an update.
_INSERTED: Label[bool] = literal_column("(xmax = 0)", Boolean).label("inserted")
_RUN_MUTABLE = (
    "status",
    "conclusion",
    "run_started_at",
    "gh_updated_at",
    "head_branch",
    "workflow_name",
    "workflow_path",
)
_JOB_MUTABLE = ("name", "status", "conclusion", "started_at", "completed_at", "labels", "steps")


def upsert_run(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    tracked_repository_id: uuid.UUID,
    batch_id: uuid.UUID | None,
    run: RunRecord,
    data_origin: str = "github_live",
) -> tuple[uuid.UUID, str]:
    """Insert or update one run attempt. Returns its row id and "inserted", "changed" or
    "unchanged"; an update only happens when a value GitHub reports has changed."""
    insert = pg_insert(CiRun).values(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        tracked_repository_id=tracked_repository_id,
        batch_id=batch_id,
        run_id=run.run_id,
        run_attempt=run.run_attempt,
        run_number=run.run_number,
        workflow_id=run.workflow_id,
        workflow_path=run.workflow_path,
        workflow_name=run.workflow_name,
        event=run.event,
        head_branch=run.head_branch,
        head_sha=run.head_sha,
        status=run.status,
        conclusion=run.conclusion,
        gh_created_at=run.created_at,
        run_started_at=run.run_started_at,
        gh_updated_at=run.updated_at,
        data_origin=data_origin,
    )
    stmt = insert.on_conflict_do_update(
        constraint="uq_ci_runs_attempt",
        set_={**{name: insert.excluded[name] for name in _RUN_MUTABLE}, "batch_id": batch_id},
        where=or_(
            *(getattr(CiRun, name).is_distinct_from(insert.excluded[name]) for name in _RUN_MUTABLE)
        ),
    ).returning(CiRun.id, _INSERTED)
    row = session.execute(stmt).one_or_none()
    if row is not None:
        return row.id, "inserted" if row.inserted else "changed"
    existing = session.execute(
        select(CiRun.id).where(
            CiRun.tracked_repository_id == tracked_repository_id,
            CiRun.run_id == run.run_id,
            CiRun.run_attempt == run.run_attempt,
        )
    ).scalar_one()
    return existing, "unchanged"


def upsert_jobs(
    session: Session, *, workspace_id: uuid.UUID, ci_run_id: uuid.UUID, jobs: list[JobRecord]
) -> Counter[str]:
    """Insert or update the jobs of one run attempt, then mark the attempt's jobs as loaded."""
    counts: Counter[str] = Counter()
    for job in jobs:
        insert = pg_insert(CiJob).values(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            ci_run_id=ci_run_id,
            job_id=job.job_id,
            name=job.name,
            status=job.status,
            conclusion=job.conclusion,
            started_at=job.started_at,
            completed_at=job.completed_at,
            labels=list(job.labels),
            steps=[step.__dict__ for step in job.steps],
        )
        stmt = insert.on_conflict_do_update(
            constraint="uq_ci_jobs_job",
            set_={name: insert.excluded[name] for name in _JOB_MUTABLE},
            where=or_(
                *(
                    getattr(CiJob, name).is_distinct_from(insert.excluded[name])
                    for name in _JOB_MUTABLE
                )
            ),
        ).returning(CiJob.id, _INSERTED)
        row = session.execute(stmt).one_or_none()
        if row is not None:
            counts["jobs_inserted" if row.inserted else "jobs_changed"] += 1
    session.execute(update(CiRun).where(CiRun.id == ci_run_id).values(jobs_synced=True))
    return counts


# ---------------------------------------------------------------------------------- sync ---


@dataclass
class _Context:
    engine: Engine
    reader: HistoryReader
    workspace_id: uuid.UUID
    tracked_id: uuid.UUID
    owner: str
    repo: str
    batch_id: uuid.UUID
    fence: Fence
    counts: Counter[str]


def _load_run(ctx: _Context, run: RunRecord, state: dict[str, Any]) -> None:
    """Store one run attempt (and the jobs of a failed one), committing it on its own."""
    if run.private:
        raise GitHubError("private_repository", "Kensa only reads public repositories.", 422)
    with Session(ctx.engine) as session, session.begin():
        ctx.fence(session)
        row_id, change = upsert_run(
            session,
            workspace_id=ctx.workspace_id,
            tracked_repository_id=ctx.tracked_id,
            batch_id=ctx.batch_id,
            run=run,
        )
        ctx.counts["runs_seen"] += 1
        ctx.counts[f"runs_{change}"] += 1
        synced = session.execute(select(CiRun.jobs_synced).where(CiRun.id == row_id)).scalar_one()
    pending = [list(p) for p in state.get("pending", [])]
    key = [run.run_id, run.run_attempt]
    if run.status != "completed":
        if key not in pending:
            pending.append(key)
    elif key in pending:
        pending.remove(key)
    state["pending"] = pending
    if run.failed and (not synced or change != "unchanged"):
        jobs = ctx.reader.jobs(ctx.owner, ctx.repo, run.run_id, run.run_attempt)
        with Session(ctx.engine) as session, session.begin():
            ctx.fence(session)
            ctx.counts.update(
                upsert_jobs(session, workspace_id=ctx.workspace_id, ci_run_id=row_id, jobs=jobs)
            )


def _load_earlier_attempts(ctx: _Context, run: RunRecord, state: dict[str, Any]) -> None:
    """A re-run lists only its latest attempt; read the earlier ones that are not stored yet,
    and a failed one whose jobs were never imported (an interrupted sync)."""
    for attempt in range(1, run.run_attempt):
        with Session(ctx.engine) as session:
            known = session.execute(
                select(CiRun.jobs_synced, CiRun.conclusion).where(
                    CiRun.tracked_repository_id == ctx.tracked_id,
                    CiRun.run_id == run.run_id,
                    CiRun.run_attempt == attempt,
                )
            ).one_or_none()
        if known is None or (not known.jobs_synced and known.conclusion in FAILED_CONCLUSIONS):
            ctx.counts["attempts_read"] += 1
            _load_run(ctx, ctx.reader.run(ctx.owner, ctx.repo, run.run_id, attempt), state)


def _save_state(ctx: _Context, state: dict[str, Any]) -> None:
    with Session(ctx.engine) as session, session.begin():
        ctx.fence(session)
        session.execute(
            update(TrackedRepository)
            .where(TrackedRepository.id == ctx.tracked_id)
            .values(sync_state=state)
        )


def _sync(ctx: _Context, state: dict[str, Any], history_days: int, now: datetime) -> None:
    batch = [list(p) for p in state.get("pending", [])][:MAX_PENDING]
    for run_id, attempt in batch:
        _load_run(ctx, ctx.reader.run(ctx.owner, ctx.repo, int(run_id), int(attempt)), state)
    # Runs still pending after their re-read go to the back, so later ones get their turn.
    pending = [list(p) for p in state.get("pending", [])]
    state["pending"] = [p for p in pending if p not in batch] + [p for p in pending if p in batch]
    _save_state(ctx, state)

    window = state.get("window")
    if window is None:
        complete = _parse(state.get("complete_through"))
        since = complete - OVERLAP if complete else now - timedelta(days=history_days)
        window = {"since": iso(since), "until": iso(now), "next_page": 1}
        state["window"] = window
        _save_state(ctx, state)
    created = f"{window['since']}..{window['until']}"
    while True:
        page = int(window["next_page"])
        runs, _total = ctx.reader.runs_page(ctx.owner, ctx.repo, created=created, page=page)
        for run in runs:
            _load_run(ctx, run, state)
            if run.run_attempt > 1:
                _load_earlier_attempts(ctx, run, state)
        listed = ctx.reader.listed  # malformed records included
        if page >= MAX_LIST_PAGES and listed == PER_PAGE and runs:
            # GitHub lists at most 1,000 runs per query, newest first: continue with a window
            # that ends at the oldest run listed so far (it is listed again: idempotent).
            oldest = min(r.created_at for r in runs)
            if iso(oldest) != window["until"]:
                ctx.counts["windows_split"] += 1
                window = {
                    "since": window["since"],
                    "until": iso(oldest),
                    "next_page": 1,
                    "final_until": window.get("final_until", window["until"]),
                }
                state["window"] = window
                created = f"{window['since']}..{window['until']}"
                _save_state(ctx, state)
                continue
            ctx.counts["listing_truncated"] += 1  # over 1,000 runs in one second
        if listed < PER_PAGE or page >= MAX_LIST_PAGES:
            state["complete_through"] = window.get("final_until", window["until"])
            state["window"] = None
            _save_state(ctx, state)
            return
        window["next_page"] = page + 1
        _save_state(ctx, state)


def sync_repository(
    engine: Engine,
    reader: HistoryReader,
    *,
    workspace_id: uuid.UUID,
    tracked_repository_id: uuid.UUID,
    now: datetime | None = None,
    fence: Fence = _no_fence,
) -> SyncOutcome:
    """Run one incremental sync and record it as an ETL batch."""
    now = now or datetime.now(UTC)
    with Session(engine) as session, session.begin():
        fence(session)
        tracked = session.execute(
            select(TrackedRepository).where(
                TrackedRepository.id == tracked_repository_id,
                TrackedRepository.workspace_id == workspace_id,
            )
        ).scalar_one()
        state: dict[str, Any] = dict(tracked.sync_state or {})
        owner, repo, history_days = tracked.owner, tracked.repo, tracked.history_days
        batch = EtlBatch(
            workspace_id=workspace_id,
            tracked_repository_id=tracked_repository_id,
            kind=SYNC_JOB,
            watermark_before=state.get("complete_through"),
        )
        session.add(batch)
        session.flush()
        batch_id = batch.id
    outcome = SyncOutcome(batch_id=batch_id, status="succeeded")
    ctx = _Context(
        engine,
        reader,
        workspace_id,
        tracked_repository_id,
        owner,
        repo,
        batch_id,
        fence,
        outcome.counts,
    )
    try:
        _sync(ctx, state, history_days, now)
    except BudgetExhaustedError:
        outcome.status = "partial"
        outcome.message = (
            "The request budget for one sync was used up; sync again to continue from here."
        )
    except GitHubError as exc:
        outcome.status = "rate_limited" if exc.code == "rate_limited" else "failed"
        outcome.error_code, outcome.message = exc.code, exc.message[:300]
    outcome.requests_used = reader.budget.used
    if reader.malformed:
        outcome.counts["malformed_skipped"] = reader.malformed
    with Session(engine) as session, session.begin():
        fence(session)
        session.execute(
            update(EtlBatch)
            .where(EtlBatch.id == batch_id)
            .values(
                status=outcome.status,
                finished_at=datetime.now(UTC),
                watermark_after=state.get("complete_through"),
                counts=dict(outcome.counts),
                requests_used=outcome.requests_used,
                error_code=outcome.error_code,
                message=outcome.message,
            )
        )
        session.execute(
            update(TrackedRepository)
            .where(TrackedRepository.id == tracked_repository_id)
            .values(sync_state=state, last_sync_at=datetime.now(UTC))
        )
    logger.info(
        "history_sync_finished",
        status=outcome.status,
        requests=outcome.requests_used,
        **dict(outcome.counts),
    )
    return outcome
