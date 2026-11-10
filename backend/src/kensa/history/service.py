"""Tracked repositories, sync jobs and the history job handler (v1.1, D-052)."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import Engine, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session

from kensa.analytics.refresh import refresh_days, run_days
from kensa.core.config import Settings
from kensa.db.models import CiRun, EtlBatch, Job, TrackedRepository
from kensa.github.client import GitHubClient, GitHubError
from kensa.history.github import FAILED_CONCLUSIONS, HistoryReader, RepositoryMeta, RequestBudget
from kensa.history.quality import run_checks
from kensa.history.sync import SYNC_JOB, sync_repository
from kensa.jobs import queue
from kensa.jobs.queue import ACTIVE_STATUSES, EnqueueResult, Lease
from kensa.jobs.worker import PermanentJobError


@dataclass(frozen=True)
class TrackedSummary:
    repository: TrackedRepository
    runs: int
    failed_runs: int
    last_batch: EtlBatch | None
    syncing: bool


def track_repository(
    session: Session, workspace_id: uuid.UUID, meta: RepositoryMeta, history_days: int
) -> tuple[TrackedRepository, bool]:
    """Track a public repository; tracking it again returns the existing row."""
    if meta.private:
        raise GitHubError("private_repository", "Kensa only reads public repositories.", 422)
    stmt = (
        pg_insert(TrackedRepository)
        .values(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            owner=meta.owner,
            repo=meta.repo,
            default_branch=meta.default_branch,
            history_days=history_days,
        )
        .on_conflict_do_nothing(constraint="uq_tracked_repositories_name")
        .returning(TrackedRepository.id)
    )
    created = session.execute(stmt).scalar_one_or_none()
    tracked = session.execute(
        select(TrackedRepository).where(
            TrackedRepository.workspace_id == workspace_id,
            TrackedRepository.owner == meta.owner,
            TrackedRepository.repo == meta.repo,
        )
    ).scalar_one()
    return tracked, created is not None


def get_tracked(
    session: Session, workspace_id: uuid.UUID, tracked_id: uuid.UUID
) -> TrackedRepository | None:
    return session.execute(
        select(TrackedRepository).where(
            TrackedRepository.id == tracked_id, TrackedRepository.workspace_id == workspace_id
        )
    ).scalar_one_or_none()


def _active_sync(session: Session, workspace_id: uuid.UUID, tracked_id: uuid.UUID) -> Job | None:
    return session.execute(
        select(Job).where(
            Job.workspace_id == workspace_id,
            Job.kind == SYNC_JOB,
            Job.status.in_(ACTIVE_STATUSES),
            Job.payload["tracked_repository_id"].astext == str(tracked_id),
        )
    ).scalar_one_or_none()


def summarize(session: Session, workspace_id: uuid.UUID) -> list[TrackedSummary]:
    rows = session.execute(
        select(TrackedRepository)
        .where(TrackedRepository.workspace_id == workspace_id)
        .order_by(TrackedRepository.owner, TrackedRepository.repo)
    ).scalars()
    summaries = []
    for tracked in rows:
        runs, failed = session.execute(
            select(
                func.count(),
                func.count().filter(CiRun.conclusion.in_(FAILED_CONCLUSIONS)),
            ).where(CiRun.tracked_repository_id == tracked.id)
        ).one()
        last = session.execute(
            select(EtlBatch)
            .where(EtlBatch.tracked_repository_id == tracked.id)
            .order_by(EtlBatch.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        syncing = _active_sync(session, workspace_id, tracked.id) is not None
        summaries.append(TrackedSummary(tracked, int(runs), int(failed), last, syncing))
    return summaries


def enqueue_sync(session: Session, workspace_id: uuid.UUID, tracked_id: uuid.UUID) -> EnqueueResult:
    """One active sync per repository: asking again while one is queued or running returns it."""
    active = _active_sync(session, workspace_id, tracked_id)
    if active is not None:
        return EnqueueResult(active.id, created=False)
    previous = session.execute(
        select(func.count()).where(
            Job.workspace_id == workspace_id,
            Job.kind == SYNC_JOB,
            Job.payload["tracked_repository_id"].astext == str(tracked_id),
        )
    ).scalar_one()
    return queue.enqueue(
        session,
        workspace_id=workspace_id,
        kind=SYNC_JOB,
        idempotency_key=f"sync:{workspace_id}:{tracked_id}:{int(previous) + 1}",
        payload={"tracked_repository_id": str(tracked_id)},
        max_attempts=2,
    )


def make_history_handler(
    settings: Settings, client_factory: Callable[[Settings], GitHubClient] | None = None
) -> Callable[[Lease, Engine], None]:
    """The ``history_sync`` job: one budgeted sync, then the data-quality checks."""

    def build(s: Settings) -> GitHubClient:
        return GitHubClient(
            token=s.github_token,
            timeout=s.github_timeout_seconds,
            max_log_bytes=s.github_max_log_bytes,
        )

    factory = client_factory or build

    def handle(lease: Lease, engine: Engine) -> None:
        raw = lease.payload.get("tracked_repository_id")
        try:
            tracked_id = uuid.UUID(str(raw))
        except ValueError as exc:
            raise PermanentJobError("invalid_payload", "The sync job names no repository.") from exc

        def fence(session: Session) -> None:
            queue.assert_lease(session, lease)

        with factory(settings) as client:
            reader = HistoryReader(client, RequestBudget(settings.history_request_budget))
            try:
                outcome = sync_repository(
                    engine,
                    reader,
                    workspace_id=lease.workspace_id,
                    tracked_repository_id=tracked_id,
                    fence=fence,
                )
            except NoResultFound as exc:
                raise PermanentJobError(
                    "repository_not_tracked", "The repository is no longer tracked."
                ) from exc
        with Session(engine) as session, session.begin():
            fence(session)
            run_checks(session, lease.workspace_id)
            refresh_days(
                session, lease.workspace_id, run_days(session, lease.workspace_id, outcome.batch_id)
            )

    return handle
