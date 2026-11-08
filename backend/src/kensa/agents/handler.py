"""Glue between the job worker and the agent graph (M3)."""

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from kensa.agents.graph import AgentConfig, run_agent
from kensa.agents.pipeline import append_event
from kensa.core.config import Settings
from kensa.db.models import Investigation
from kensa.inference.factory import embedder_for, provider_for
from kensa.jobs.queue import Lease
from kensa.jobs.worker import Handler, JobOutcome, PermanentJobError

USER_MESSAGES = {
    "model_unavailable": (
        "The local model server (Ollama) is not reachable. Start Ollama, then retry."
    ),
    "model_missing": "The configured model is not downloaded in Ollama.",
    "inference_timeout": "The local model did not answer in time.",
    "inference_error": "The local model returned an error.",
    "worker_lost": "The background worker stopped responding on the final attempt.",
    "internal_error": "An unexpected internal error occurred.",
    "invalid_job": "The investigation job was malformed.",
    "lease_lost": "The background worker lost its claim on this investigation.",
}


def user_message(code: str) -> str:
    return USER_MESSAGES.get(code, "The investigation failed.")


def make_investigate_handler(settings: Settings) -> Handler:
    """Handles both job kinds: ``investigate`` starts (or, after a crash, resumes) the graph;
    ``resume`` continues it past the approval interrupt once a decision is recorded. Either
    kind drives the graph as far as its checkpoint and the recorded decision allow."""

    def handle(lease: Lease, engine: Engine) -> None:
        if lease.investigation_id is None:
            raise PermanentJobError("invalid_job", "investigate job without an investigation")
        with Session(engine) as session:
            provider_name = session.scalar(
                select(Investigation.provider).where(
                    Investigation.id == lease.investigation_id,
                    Investigation.workspace_id == lease.workspace_id,
                )
            )
        if provider_name is None:
            raise PermanentJobError("invalid_job", "investigation not found")
        provider = provider_for(provider_name, settings)
        run_agent(
            lease,
            engine,
            provider,
            database_url=settings.database_url.get_secret_value(),
            config=AgentConfig.from_settings(settings),
            embedder=embedder_for(settings),
        )

    return handle


def on_job_outcome(engine: Engine, outcome: JobOutcome) -> None:
    """Reflect a retry or a final failure on the investigation and its timeline."""
    if outcome.investigation_id is None:
        return
    with Session(engine) as session, session.begin():
        investigation = session.execute(
            select(Investigation)
            .where(Investigation.id == outcome.investigation_id)
            .with_for_update()
        ).scalar_one_or_none()
        if investigation is None:
            return
        message = user_message(outcome.code)
        investigation.error_code = outcome.code
        investigation.error_message = message
        if outcome.outcome == "dead":
            investigation.status = "failed"
            investigation.finished_at = func.now()
            summary = f"Investigation failed: {message}"
        else:
            investigation.status = "queued"
            summary = f"Attempt {outcome.attempt} failed ({outcome.code}); retrying with backoff."
        append_event(
            session,
            workspace_id=investigation.workspace_id,
            investigation_id=investigation.id,
            attempt=outcome.attempt,
            node="pipeline",
            event_type="failed" if outcome.outcome == "dead" else "info",
            summary=summary,
        )
