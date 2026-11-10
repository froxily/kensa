"""Leased PostgreSQL job queue (DECISIONS.md D-006).

Protocol:
* ``enqueue``: a unique idempotency key, and at most one active (queued/running) job per
  investigation. Re-enqueueing returns the existing job instead of creating a duplicate.
* ``claim``: ``FOR UPDATE SKIP LOCKED`` over due queued jobs and running jobs whose lease has
  expired. Claiming increments ``attempts``, which doubles as the fencing token.
* ``heartbeat`` / ``complete`` / ``fail`` / ``assert_lease`` only succeed while the caller
  still holds the lease (same owner, same attempt, status running). A worker that stalled and
  lost its lease can therefore never overwrite the work of the worker that reclaimed the job.

All times come from the database clock (``now()``), never from the workers' clocks.
"""

import random
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import and_, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from kensa.db.models import Job

ACTIVE_STATUSES = ("queued", "running")
BACKOFF_BASE_SECONDS = 2.0
BACKOFF_MAX_SECONDS = 60.0


class LeaseLostError(RuntimeError):
    """The caller no longer holds the job's lease; it must stop writing."""


@dataclass(frozen=True)
class Lease:
    job_id: uuid.UUID
    owner: str
    attempt: int
    max_attempts: int
    kind: str
    workspace_id: uuid.UUID
    investigation_id: uuid.UUID | None
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def is_final_attempt(self) -> bool:
        return self.attempt >= self.max_attempts


@dataclass(frozen=True)
class EnqueueResult:
    job_id: uuid.UUID
    created: bool


def enqueue(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    kind: str,
    idempotency_key: str,
    investigation_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
    max_attempts: int = 3,
) -> EnqueueResult:
    stmt = (
        pg_insert(Job)
        .values(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            kind=kind,
            idempotency_key=idempotency_key,
            investigation_id=investigation_id,
            payload=payload or {},
            max_attempts=max_attempts,
        )
        # No conflict target: covers both the idempotency key and the one-active-job index.
        .on_conflict_do_nothing()
        .returning(Job.id)
    )
    created_id = session.execute(stmt).scalar_one_or_none()
    if created_id is not None:
        return EnqueueResult(created_id, created=True)

    conditions = [Job.idempotency_key == idempotency_key]
    if investigation_id is not None:
        conditions.append(
            and_(Job.investigation_id == investigation_id, Job.status.in_(ACTIVE_STATUSES))
        )
    existing = session.execute(
        select(Job.id).where(or_(*conditions)).order_by(Job.created_at.desc()).limit(1)
    ).scalar_one()
    return EnqueueResult(existing, created=False)


_CLAIM = text(
    """
    WITH next AS (
        SELECT id FROM jobs
        WHERE ((status = 'queued' AND run_after <= now())
               OR (status = 'running' AND lease_expires_at < now() AND attempts < max_attempts))
          AND (CAST(:kinds AS text[]) IS NULL OR kind = ANY(CAST(:kinds AS text[])))
          AND (CAST(:exclude AS text[]) IS NULL OR NOT kind = ANY(CAST(:exclude AS text[])))
        ORDER BY run_after, created_at
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    UPDATE jobs AS j
    SET status = 'running',
        attempts = j.attempts + 1,
        lease_owner = :owner,
        lease_expires_at = now() + make_interval(secs => :lease_seconds),
        heartbeat_at = now(),
        updated_at = now()
    FROM next
    WHERE j.id = next.id
    RETURNING j.id, j.kind, j.payload, j.attempts, j.max_attempts, j.workspace_id,
              j.investigation_id
    """
)


def claim(
    session: Session,
    owner: str,
    lease_seconds: float,
    kinds: Sequence[str] | None = None,
    exclude: Sequence[str] | None = None,
) -> Lease | None:
    """Claim the next due job. ``kinds`` limits it to those kinds; ``exclude`` skips kinds
    (v1.1: the history worker takes only syncs, the agent worker everything else)."""
    params = {
        "owner": owner,
        "lease_seconds": lease_seconds,
        "kinds": _kinds(kinds),
        "exclude": _kinds(exclude),
    }
    row = session.execute(_CLAIM, params).one_or_none()
    if row is None:
        return None
    return Lease(
        job_id=row.id,
        owner=owner,
        attempt=row.attempts,
        max_attempts=row.max_attempts,
        kind=row.kind,
        workspace_id=row.workspace_id,
        investigation_id=row.investigation_id,
        payload=dict(row.payload or {}),
    )


@dataclass(frozen=True)
class ReapedJob:
    job_id: uuid.UUID
    investigation_id: uuid.UUID | None
    attempt: int


_REAP = text(
    """
    UPDATE jobs
    SET status = 'dead', last_error = 'worker_lost: lease expired on the final attempt',
        lease_owner = NULL, lease_expires_at = NULL, finished_at = now(), updated_at = now()
    WHERE status = 'running' AND lease_expires_at < now() AND attempts >= max_attempts
      AND (CAST(:kinds AS text[]) IS NULL OR kind = ANY(CAST(:kinds AS text[])))
      AND (CAST(:exclude AS text[]) IS NULL OR NOT kind = ANY(CAST(:exclude AS text[])))
    RETURNING id, investigation_id, attempts
    """
)


def reap_expired(
    session: Session, kinds: Sequence[str] | None = None, exclude: Sequence[str] | None = None
) -> list[ReapedJob]:
    """Jobs whose worker died on their last allowed attempt: they will never be reclaimed.
    ``kinds`` and ``exclude`` work as in ``claim``, so each worker reports its own jobs."""
    rows = session.execute(_REAP, {"kinds": _kinds(kinds), "exclude": _kinds(exclude)})
    return [ReapedJob(r.id, r.investigation_id, r.attempts) for r in rows]


def _kinds(kinds: Sequence[str] | None) -> list[str] | None:
    return None if kinds is None else sorted(kinds)


# Every statement below ends in the same fence: the caller's owner and attempt must still hold
# the running job. Written out in full so each statement is a plain literal.
_ASSERT_LEASE = text(
    """
    SELECT 1 FROM jobs
    WHERE id = :job_id AND lease_owner = :owner AND attempts = :attempt AND status = 'running'
    FOR UPDATE
    """
)
_HEARTBEAT = text(
    """
    UPDATE jobs
    SET lease_expires_at = now() + make_interval(secs => :lease_seconds),
        heartbeat_at = now(), updated_at = now()
    WHERE id = :job_id AND lease_owner = :owner AND attempts = :attempt AND status = 'running'
    """
)
_COMPLETE = text(
    """
    UPDATE jobs
    SET status = 'succeeded', lease_owner = NULL, lease_expires_at = NULL,
        finished_at = now(), updated_at = now(), last_error = NULL
    WHERE id = :job_id AND lease_owner = :owner AND attempts = :attempt AND status = 'running'
    """
)
_RETRY = text(
    """
    UPDATE jobs
    SET status = 'queued', lease_owner = NULL, lease_expires_at = NULL,
        run_after = now() + make_interval(secs => :delay), last_error = :error,
        updated_at = now()
    WHERE id = :job_id AND lease_owner = :owner AND attempts = :attempt AND status = 'running'
    """
)
_DEAD = text(
    """
    UPDATE jobs
    SET status = 'dead', lease_owner = NULL, lease_expires_at = NULL,
        last_error = :error, finished_at = now(), updated_at = now()
    WHERE id = :job_id AND lease_owner = :owner AND attempts = :attempt AND status = 'running'
    """
)


def _fence_params(lease: Lease) -> dict[str, Any]:
    return {"job_id": lease.job_id, "owner": lease.owner, "attempt": lease.attempt}


def assert_lease(session: Session, lease: Lease) -> None:
    """Lock the job row and verify the lease is still ours. Call first in every write
    transaction a handler makes; the row lock holds until that transaction ends."""
    held = session.execute(_ASSERT_LEASE, _fence_params(lease)).scalar_one_or_none()
    if held is None:
        raise LeaseLostError(f"lease on job {lease.job_id} attempt {lease.attempt} was lost")


def _updated(session: Session, statement: Any, params: dict[str, Any]) -> bool:
    return bool(session.execute(statement, params).rowcount)  # type: ignore[attr-defined]


def heartbeat(session: Session, lease: Lease, lease_seconds: float) -> bool:
    return _updated(session, _HEARTBEAT, {**_fence_params(lease), "lease_seconds": lease_seconds})


def complete(session: Session, lease: Lease) -> bool:
    return _updated(session, _COMPLETE, _fence_params(lease))


def backoff_seconds(attempt: int) -> float:
    base = min(BACKOFF_MAX_SECONDS, BACKOFF_BASE_SECONDS * 2.0 ** (attempt - 1))
    return base * random.uniform(0.5, 1.5)  # noqa: S311  (jitter, not cryptography)


FailOutcome = Literal["retry", "dead", "lost"]


def fail(session: Session, lease: Lease, error: str, *, retryable: bool) -> FailOutcome:
    """Record a failed attempt: re-queue with backoff while attempts remain, else mark dead."""
    params = {**_fence_params(lease), "error": error[:500]}
    if retryable and not lease.is_final_attempt:
        params["delay"] = backoff_seconds(lease.attempt)
        return "retry" if _updated(session, _RETRY, params) else "lost"
    return "dead" if _updated(session, _DEAD, params) else "lost"
