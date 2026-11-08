"""The leased job queue and worker: the M1 worker test matrix (ROADMAP.md)."""

import threading
import time
import uuid
from datetime import datetime

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from kensa.db.models import DEFAULT_WORKSPACE_ID, AgentEvent, Investigation, Job
from kensa.jobs import queue
from kensa.jobs.queue import EnqueueResult, Lease, LeaseLostError
from kensa.jobs.worker import (
    JobOutcome,
    PermanentJobError,
    RetryableJobError,
    Worker,
)

pytestmark = pytest.mark.db


def _investigation(engine: Engine) -> uuid.UUID:
    with Session(engine) as session, session.begin():
        inv = Investigation(
            workspace_id=DEFAULT_WORKSPACE_ID, title="t", source="paste", provider="mock"
        )
        session.add(inv)
        session.flush()
        return inv.id


def _enqueue(
    engine: Engine, key: str = "k1", inv: uuid.UUID | None = None, max_attempts: int = 3
) -> EnqueueResult:
    with Session(engine) as session, session.begin():
        return queue.enqueue(
            session,
            workspace_id=DEFAULT_WORKSPACE_ID,
            kind="test",
            idempotency_key=key,
            investigation_id=inv,
            max_attempts=max_attempts,
        )


def _claim(engine: Engine, owner: str = "A", lease_seconds: float = 30.0) -> Lease | None:
    with Session(engine) as session, session.begin():
        return queue.claim(session, owner, lease_seconds)


def _job(engine: Engine, job_id: uuid.UUID) -> Job:
    with Session(engine, expire_on_commit=False) as session:
        return session.get_one(Job, job_id)


def _sql(engine: Engine, statement: str, job_id: uuid.UUID) -> None:
    with engine.begin() as conn:
        conn.execute(text(statement), {"id": job_id})


def _expire(engine: Engine, job_id: uuid.UUID) -> None:
    _sql(
        engine,
        "UPDATE jobs SET lease_expires_at = now() - interval '1 second' WHERE id = :id",
        job_id,
    )


def _make_due(engine: Engine, job_id: uuid.UUID) -> None:
    _sql(engine, "UPDATE jobs SET run_after = now() WHERE id = :id", job_id)


def test_enqueue_is_idempotent(db_engine: Engine) -> None:
    first = _enqueue(db_engine, "same")
    second = _enqueue(db_engine, "same")
    assert first.created
    assert not second.created
    assert first.job_id == second.job_id
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 1


def test_one_active_job_per_investigation(db_engine: Engine) -> None:
    inv = _investigation(db_engine)
    first = _enqueue(db_engine, "a", inv)
    duplicate = _enqueue(db_engine, "b", inv)
    assert duplicate.job_id == first.job_id
    assert not duplicate.created

    lease = _claim(db_engine)
    assert lease is not None
    with Session(db_engine) as session, session.begin():
        assert queue.complete(session, lease)
    after_completion = _enqueue(db_engine, "c", inv)
    assert after_completion.created
    assert after_completion.job_id != first.job_id


def test_concurrent_claims_never_double_process(db_engine: Engine) -> None:
    job_ids = {_enqueue(db_engine, f"job-{i}").job_id for i in range(5)}
    barrier = threading.Barrier(8)
    claimed: list[uuid.UUID] = []
    lock = threading.Lock()

    def worker(n: int) -> None:
        barrier.wait()
        while (lease := _claim(db_engine, owner=f"w{n}")) is not None:
            with lock:
                claimed.append(lease.job_id)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(claimed) == sorted(job_ids)  # every job exactly once


def test_expired_lease_is_reclaimed_and_stale_writes_are_rejected(db_engine: Engine) -> None:
    job_id = _enqueue(db_engine).job_id
    stale = _claim(db_engine, "A")
    assert stale is not None
    _expire(db_engine, job_id)

    fresh = _claim(db_engine, "B")
    assert fresh is not None
    assert (fresh.job_id, fresh.attempt) == (job_id, 2)

    with Session(db_engine) as session, session.begin(), pytest.raises(LeaseLostError):
        queue.assert_lease(session, stale)
    with Session(db_engine) as session, session.begin():
        assert not queue.heartbeat(session, stale, 30)
        assert not queue.complete(session, stale)
        assert queue.fail(session, stale, "x", retryable=True) == "lost"
    with Session(db_engine) as session, session.begin():
        assert queue.complete(session, fresh)
    job = _job(db_engine, job_id)
    assert (job.status, job.attempts, job.lease_owner) == ("succeeded", 2, None)


def test_killed_worker_job_completes_exactly_once(db_engine: Engine) -> None:
    inv = _investigation(db_engine)
    job_id = _enqueue(db_engine, inv=inv).job_id

    def handler(lease: Lease, engine: Engine) -> None:
        with Session(engine) as session, session.begin():
            queue.assert_lease(session, lease)
            session.add(
                AgentEvent(
                    workspace_id=DEFAULT_WORKSPACE_ID,
                    investigation_id=inv,
                    seq=1,
                    attempt=lease.attempt,
                    node="test",
                    event_type="completed",
                    summary="side effect",
                )
            )

    crashed = _claim(db_engine, "A")  # worker A claims, then "dies" before doing anything
    assert crashed is not None
    _expire(db_engine, job_id)

    assert Worker(db_engine, {"test": handler}, owner="B").run_once()
    with pytest.raises(LeaseLostError):  # A wakes up later: its write is fenced off
        handler(crashed, db_engine)

    with Session(db_engine) as session:
        events = session.scalars(select(AgentEvent)).all()
    assert [(e.seq, e.attempt) for e in events] == [(1, 2)]
    assert _job(db_engine, job_id).status == "succeeded"


def test_retries_are_bounded_then_dead(db_engine: Engine) -> None:
    inv = _investigation(db_engine)
    job_id = _enqueue(db_engine, inv=inv, max_attempts=3).job_id
    outcomes: list[JobOutcome] = []

    def flaky(lease: Lease, engine: Engine) -> None:
        raise RetryableJobError("model_unavailable", "Ollama is not running.")

    worker = Worker(
        db_engine, {"test": flaky}, owner="W", on_outcome=lambda _, o: outcomes.append(o)
    )
    assert worker.run_once()
    job = _job(db_engine, job_id)
    assert job.status == "queued"
    assert job.run_after is not None
    assert job.run_after > datetime.now(job.run_after.tzinfo)
    assert not worker.run_once()  # backoff: not due yet

    for _ in range(2):
        _make_due(db_engine, job_id)
        assert worker.run_once()

    job = _job(db_engine, job_id)
    assert (job.status, job.attempts) == ("dead", 3)
    assert job.last_error == "model_unavailable: Ollama is not running."
    assert [o.outcome for o in outcomes] == ["retry", "retry", "dead"]
    assert all(o.code == "model_unavailable" and o.investigation_id == inv for o in outcomes)
    _make_due(db_engine, job_id)
    assert not worker.run_once()  # dead jobs are never claimed again


def test_permanent_error_is_not_retried(db_engine: Engine) -> None:
    job_id = _enqueue(db_engine).job_id
    outcomes: list[JobOutcome] = []

    def broken(lease: Lease, engine: Engine) -> None:
        raise PermanentJobError("invalid_input", "Nothing to analyse.")

    Worker(db_engine, {"test": broken}, on_outcome=lambda _, o: outcomes.append(o)).run_once()
    job = _job(db_engine, job_id)
    assert (job.status, job.attempts) == ("dead", 1)
    assert [(o.outcome, o.code) for o in outcomes] == [("dead", "invalid_input")]


def test_unexpected_exception_is_retried(db_engine: Engine) -> None:
    job_id = _enqueue(db_engine).job_id
    outcomes: list[JobOutcome] = []

    def buggy(lease: Lease, engine: Engine) -> None:
        raise ValueError("boom")

    Worker(db_engine, {"test": buggy}, on_outcome=lambda _, o: outcomes.append(o)).run_once()
    assert _job(db_engine, job_id).status == "queued"
    assert [(o.outcome, o.code) for o in outcomes] == [("retry", "internal_error")]


def test_unknown_kind_is_dead(db_engine: Engine) -> None:
    job_id = _enqueue(db_engine).job_id
    Worker(db_engine, {}).run_once()
    job = _job(db_engine, job_id)
    assert job.status == "dead"
    assert job.last_error is not None
    assert job.last_error.startswith("unknown_job_kind")


def test_lease_expired_on_final_attempt_is_reaped(db_engine: Engine) -> None:
    inv = _investigation(db_engine)
    job_id = _enqueue(db_engine, inv=inv, max_attempts=1).job_id
    assert _claim(db_engine, "A") is not None
    _expire(db_engine, job_id)
    outcomes: list[JobOutcome] = []

    claimed = Worker(db_engine, {}, owner="B", on_outcome=lambda _, o: outcomes.append(o))
    assert not claimed.run_once()
    assert _job(db_engine, job_id).status == "dead"
    assert [(o.outcome, o.code, o.investigation_id) for o in outcomes] == [
        ("dead", "worker_lost", inv)
    ]


def test_heartbeat_extends_lease(db_engine: Engine) -> None:
    job_id = _enqueue(db_engine).job_id
    lease = _claim(db_engine, lease_seconds=30)
    assert lease is not None
    _sql(
        db_engine,
        "UPDATE jobs SET lease_expires_at = now() + interval '1 second' WHERE id = :id",
        job_id,
    )
    before = _job(db_engine, job_id).lease_expires_at
    with Session(db_engine) as session, session.begin():
        assert queue.heartbeat(session, lease, 30)
    after = _job(db_engine, job_id).lease_expires_at
    assert before is not None
    assert after is not None
    assert after > before


def test_backoff_is_bounded() -> None:
    assert all(1.0 <= queue.backoff_seconds(1) <= 3.0 for _ in range(50))
    assert all(queue.backoff_seconds(20) <= queue.BACKOFF_MAX_SECONDS * 1.5 for _ in range(50))


def test_worker_thread_processes_jobs_and_stops(db_engine: Engine) -> None:
    job_id = _enqueue(db_engine).job_id
    done = threading.Event()

    def handler(lease: Lease, engine: Engine) -> None:
        done.set()

    stop = threading.Event()
    worker = Worker(db_engine, {"test": handler}, poll_seconds=0.05)
    thread = threading.Thread(target=worker.run_forever, args=(stop,))
    thread.start()
    try:
        assert done.wait(10)
        deadline = time.monotonic() + 10
        while _job(db_engine, job_id).status != "succeeded" and time.monotonic() < deadline:
            time.sleep(0.05)
        assert _job(db_engine, job_id).status == "succeeded"
    finally:
        stop.set()
        thread.join(timeout=10)
    assert not thread.is_alive()
