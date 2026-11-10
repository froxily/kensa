"""In-process job worker: claims leased jobs and runs their handlers.

Handlers receive the lease and must call ``queue.assert_lease`` at the start of every write
transaction, so that a worker which stalled past its lease cannot commit stale results.
"""

import os
import socket
import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import structlog
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from kensa.core.telemetry import tracer
from kensa.jobs import queue
from kensa.jobs.queue import Lease, LeaseLostError

logger = structlog.get_logger(__name__)


class JobError(Exception):
    """A handler failure with a stable error code (shown to users, stored on the job)."""

    retryable: bool = True

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class RetryableJobError(JobError):
    retryable = True


class PermanentJobError(JobError):
    retryable = False


@dataclass(frozen=True)
class JobOutcome:
    """Reported to the outcome listener when a job is re-queued or ends dead."""

    job_id: uuid.UUID
    investigation_id: uuid.UUID | None
    outcome: str  # "retry" | "dead"
    code: str
    message: str
    attempt: int


Handler = Callable[[Lease, Engine], None]
OutcomeListener = Callable[[Engine, JobOutcome], None]


def default_owner() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


class Worker:
    def __init__(
        self,
        engine: Engine,
        handlers: Mapping[str, Handler],
        *,
        owner: str | None = None,
        lease_seconds: float = 30.0,
        heartbeat_seconds: float = 10.0,
        poll_seconds: float = 1.0,
        on_outcome: OutcomeListener | None = None,
        only_handled: bool = False,
        exclude: Sequence[str] = (),
    ) -> None:
        self.engine = engine
        self.handlers = dict(handlers)
        # By default a worker claims any job, so one of an unknown kind ends dead instead of
        # waiting forever; ``exclude`` leaves kinds to another worker. A worker with
        # ``only_handled`` (v1.1: the history worker) claims and reaps only its own kinds.
        self.kinds: tuple[str, ...] | None = tuple(sorted(self.handlers)) if only_handled else None
        self.exclude = tuple(sorted(exclude)) or None
        self.owner = owner or default_owner()
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.poll_seconds = poll_seconds
        self.on_outcome = on_outcome

    def _report(self, outcome: JobOutcome) -> None:
        if self.on_outcome is None:
            return
        try:
            self.on_outcome(self.engine, outcome)
        except Exception:
            logger.exception("job_outcome_listener_failed", job_id=str(outcome.job_id))

    def run_once(self) -> bool:
        """Reap jobs abandoned on their final attempt, then claim and run one job.
        Returns whether a job was claimed."""
        with Session(self.engine) as session, session.begin():
            reaped = queue.reap_expired(session, self.kinds, self.exclude)
        for job in reaped:
            self._report(
                JobOutcome(
                    job.job_id,
                    job.investigation_id,
                    "dead",
                    "worker_lost",
                    "The worker stopped responding on the final attempt.",
                    job.attempt,
                )
            )

        with Session(self.engine) as session, session.begin():
            lease = queue.claim(session, self.owner, self.lease_seconds, self.kinds, self.exclude)
        if lease is None:
            return False
        self._process(lease)
        return True

    def _heartbeat_loop(self, lease: Lease, stop: threading.Event) -> None:
        while not stop.wait(self.heartbeat_seconds):
            with Session(self.engine) as session, session.begin():
                if not queue.heartbeat(session, lease, self.lease_seconds):
                    logger.warning("job_lease_lost", job_id=str(lease.job_id))
                    return

    def _process(self, lease: Lease) -> None:
        log = logger.bind(job_id=str(lease.job_id), kind=lease.kind, attempt=lease.attempt)
        stop = threading.Event()
        beat = threading.Thread(target=self._heartbeat_loop, args=(lease, stop), daemon=True)
        beat.start()
        error: JobError | None = None
        try:
            handler = self.handlers.get(lease.kind)
            if handler is None:
                raise PermanentJobError("unknown_job_kind", f"No handler for '{lease.kind}'.")
            with (
                tracer.start_as_current_span(
                    f"job.{lease.kind}",
                    attributes={
                        "kensa.job_id": str(lease.job_id),
                        "kensa.attempt": lease.attempt,
                        "kensa.investigation_id": str(lease.investigation_id),
                    },
                ),
                structlog.contextvars.bound_contextvars(
                    job_id=str(lease.job_id), investigation_id=str(lease.investigation_id)
                ),
            ):
                handler(lease, self.engine)
        except LeaseLostError:
            log.warning("job_abandoned_lease_lost")
            return
        except JobError as exc:
            error = exc
        except Exception as exc:  # unexpected: retry, bounded by max_attempts
            log.exception("job_handler_crashed")
            error = RetryableJobError("internal_error", type(exc).__name__)
        finally:
            stop.set()
            beat.join(timeout=5)

        with Session(self.engine) as session, session.begin():
            if error is None:
                if not queue.complete(session, lease):
                    log.warning("job_completion_rejected_lease_lost")
                return
            result = queue.fail(
                session, lease, f"{error.code}: {error.message}", retryable=error.retryable
            )
        log.info("job_failed", code=error.code, result=result)
        if result in ("retry", "dead"):
            self._report(
                JobOutcome(
                    lease.job_id,
                    lease.investigation_id,
                    result,
                    error.code,
                    error.message,
                    lease.attempt,
                )
            )

    def run_forever(self, stop: threading.Event) -> None:
        log = logger.bind(owner=self.owner)
        log.info("worker_started")
        while not stop.is_set():
            try:
                claimed = self.run_once()
            except Exception:
                log.exception("worker_loop_error")
                claimed = False
            if not claimed:
                stop.wait(self.poll_seconds)
        log.info("worker_stopped")
