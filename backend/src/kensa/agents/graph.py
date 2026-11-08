"""The M3 agent workflow: a LangGraph StateGraph over the pipeline steps (DECISIONS.md D-028).

    collect_evidence → retrieve → assess_completeness ─┬─ no failure shown ──────────→ abstain
                          ↑      (targeted, ≤ rounds)   ├─ failure lines missing → retrieve
                          └─────────────────────────────┴─ sufficient → diagnose → verify
    verify ─┬─ rejected, retries and budget left → diagnose (with the verifier's feedback)
            └─ accepted or exhausted → plan_remediation
    abstain / plan_remediation → persist_report ─┬─ no proposals → END (completed)
                                                 └─ approval (interrupt) → record_decision
    record_decision → finalize → END

Guarantees:
* Durable: a PostgreSQL checkpoint is written after every step (``durability="sync"``), so a
  worker that dies is replaced by one that resumes from the last finished step.
* Fenced: every database write, checkpoints included, first re-checks the job lease (D-006).
* Bounded: diagnosis attempts, targeted retrieval rounds, model calls and wall-clock time.
* Human in the loop: ``persist_report`` saves the report and the proposals *before* the approval
  interrupt; the approval node has no side effects before ``interrupt()``; the decision itself
  is recorded by the API (``kensa.investigations.service.decide``), exactly once.
* Read-only: no node writes to a repository or executes anything from the evidence.
"""

import hashlib
import json
import os
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import Any, Literal, cast

import psycopg
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import ChannelVersions, Checkpoint, CheckpointMetadata
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt
from psycopg.rows import DictRow, dict_row
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from kensa.agents.completeness import assess, scan_log
from kensa.agents.evidence import EvidenceItem, evidence_lines
from kensa.agents.pipeline import (
    InvestigationState,
    Recorder,
    append_event,
    classify_node,
    collect_evidence,
    deterministic_fallback,
    fenced,
    index_incident,
    index_node,
    persist_report,
    retrieve_node,
    rules_only_draft,
)
from kensa.agents.prompts import (
    build_messages,
    build_planner_messages,
    evidence_budget_chars,
    fit_to_budget,
    retry_messages,
)
from kensa.agents.remediation import (
    CATEGORY_RISKS,
    CATEGORY_VALIDATION,
    MAX_PROPOSALS,
    REPOSITORY_SOURCES,
    Proposal,
    RepositoryFile,
    fix_proposals,
    validate_edit,
)
from kensa.agents.schemas import DiagnosisDraft, RemediationDraft
from kensa.agents.state import (
    GraphState,
    Json,
    completeness_to_json,
    evidence_from_json,
    evidence_to_json,
    result_from_json,
    result_to_json,
    rule_from_json,
    rule_to_json,
    scan_from_json,
    scan_to_json,
    signature_from_json,
    signature_to_json,
    verification_from_json,
    verification_to_json,
)
from kensa.agents.verifier import Verification, verify
from kensa.analysis.causes import causes_from_json, causes_to_json
from kensa.core.config import Settings
from kensa.core.telemetry import traced, tracer
from kensa.db.models import (
    ApprovalDecision,
    Chunk,
    Document,
    Investigation,
    RemediationProposal,
)
from kensa.inference.base import (
    InferenceError,
    InferenceProvider,
    MalformedOutputError,
    StructuredRequest,
    StructuredResult,
)
from kensa.inference.embeddings import Embedder
from kensa.jobs import queue
from kensa.jobs.queue import Lease
from kensa.jobs.worker import PermanentJobError, RetryableJobError
from kensa.retrieval.search import ALL_CHANNELS

CHECKPOINT_SCHEMA = "langgraph"
STATUS_RANK = {"not_established": 0, "conflicting": 1, "plausible": 2, "corroborated": 3}
TRACING_VARIABLES = ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING")
# A run passes at most ~20 steps (collect, 3 retrievals, 3 assessments, 3 diagnose/verify
# pairs, plan, persist, approval, record, finalize); the limit only guards against a bug.
RECURSION_LIMIT = 60
MAX_DRIVE_ROUNDS = 3


def disable_tracing() -> None:
    """LangSmith stays off (a project rule): force it off here, whatever the shell has."""
    for name in TRACING_VARIABLES:
        os.environ[name] = "false"


def thread_id(investigation_id: uuid.UUID) -> str:
    return f"investigation-{investigation_id}"


@dataclass(frozen=True)
class AgentConfig:
    num_ctx: int
    channels: frozenset[str] = ALL_CHANNELS
    index_incidents: bool = False
    max_diagnosis_attempts: int = 3
    max_retrieval_rounds: int = 2
    max_llm_calls: int = 4
    max_seconds: float = 900.0
    remediation_diffs: bool = True

    @classmethod
    def from_settings(
        cls, settings: Settings, channels: frozenset[str] | None = None
    ) -> "AgentConfig":
        return cls(
            num_ctx=settings.llm_num_ctx,
            channels=channels if channels is not None else frozenset(settings.retrieval_channels),
            index_incidents=settings.index_incidents,
            max_diagnosis_attempts=settings.agent_max_diagnosis_attempts,
            max_retrieval_rounds=settings.agent_max_retrieval_rounds,
            max_llm_calls=settings.agent_max_llm_calls,
            max_seconds=settings.agent_max_seconds,
            remediation_diffs=settings.remediation_diffs,
        )


# ---------------------------------------------------------------------------- checkpoints ---


class FencedPostgresSaver(PostgresSaver):
    """PostgresSaver whose writes first re-check the job lease, so a worker that lost its lease
    cannot advance the thread that the worker which reclaimed the job is now running."""

    def __init__(self, conn: psycopg.Connection[DictRow], fence: Callable[[], None]) -> None:
        # Strict deserialization: the state holds only JSON-like values (kensa.agents.state).
        super().__init__(conn, serde=JsonPlusSerializer(allowed_msgpack_modules=None))
        self._fence = fence

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        self._fence()
        return super().put(config, checkpoint, metadata, new_versions)

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Any,
        task_id: str,
        task_path: str = "",
    ) -> None:
        self._fence()
        super().put_writes(config, writes, task_id, task_path)


def libpq_url(database_url: str) -> str:
    return make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)


@contextmanager
def open_checkpointer(
    database_url: str, fence: Callable[[], None]
) -> Iterator[FencedPostgresSaver]:
    """One connection per job run; the tables live in their own schema (migration 0004)."""
    with psycopg.Connection.connect(
        libpq_url(database_url),
        autocommit=True,
        prepare_threshold=0,
        row_factory=dict_row,
        options=f"-c search_path={CHECKPOINT_SCHEMA}",
    ) as conn:
        yield FencedPostgresSaver(conn, fence)


def lease_fence(engine: Engine, lease: Lease) -> Callable[[], None]:
    def fence() -> None:
        with Session(engine) as session, session.begin():
            queue.assert_lease(session, lease)

    return fence


# -------------------------------------------------------------------------------- context ---


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


@dataclass
class RunContext:
    engine: Engine
    lease: Lease
    provider: InferenceProvider
    embedder: Embedder | None
    config: AgentConfig
    started: float = field(default_factory=time.perf_counter)

    def emit(
        self,
        state: GraphState,
        node: str,
        event_type: str,
        summary: str,
        *,
        detail: dict[str, Any] | None = None,
        duration_ms: int | None = None,
    ) -> None:
        with fenced(self.engine, self.lease) as session:
            append_event(
                session,
                workspace_id=uuid.UUID(state["workspace_id"]),
                investigation_id=uuid.UUID(state["investigation_id"]),
                attempt=self.lease.attempt,
                node=node,
                event_type=event_type,
                summary=summary,
                detail=detail,
                duration_ms=duration_ms,
            )

    def can_call_model(self, state: GraphState) -> bool:
        within_time = time.perf_counter() - self.started < self.config.max_seconds
        return within_time and state.get("llm_calls", 0) < self.config.max_llm_calls


def pipeline_state(state: GraphState) -> InvestigationState:
    """Rebuild the pipeline's working state from the graph state."""
    st = InvestigationState(
        uuid.UUID(state["investigation_id"]), uuid.UUID(state["workspace_id"]), state["title"]
    )
    st.repository_id = uuid.UUID(state["repository_id"]) if state["repository_id"] else None
    st.channels = frozenset(state["channels"])
    st.signatures = [signature_from_json(s) for s in state.get("signatures", [])]
    st.document_count = state.get("document_count", 0)
    st.line_count = state.get("line_count", 0)
    st.log_tail = list(state.get("log_tail", []))
    st.rule = rule_from_json(state["rule"]) if "rule" in state else None
    st.causes = causes_from_json(state.get("causes", []))
    st.evidence = [evidence_from_json(e) for e in state.get("evidence", [])]
    best = state.get("best")
    if best:
        st.inference = result_from_json(best["result"]) if best["result"] else None
        st.malformed = bool(best.get("malformed"))
        st.verification = verification_from_json(best["verification"])
    return st


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


def _job_error(exc: InferenceError) -> RetryableJobError | PermanentJobError:
    error_type = RetryableJobError if exc.retryable else PermanentJobError
    return error_type(exc.code, str(exc))


# ---------------------------------------------------------------------------------- nodes ---


def collect_node(ctx: RunContext, state: GraphState) -> dict[str, Any]:
    started = time.perf_counter()
    st = pipeline_state(state)
    with Session(ctx.engine) as session:
        collect_evidence(session, st)
        content = session.scalar(
            select(Document.content)
            .where(Document.investigation_id == st.investigation_id, Document.source_type == "log")
            .order_by(Document.created_at)
            .limit(1)
        )
    scan = scan_log((content or "").split("\n"))
    ctx.emit(
        state,
        "collect_evidence",
        "completed",
        f"{st.document_count} log, {st.line_count} lines, "
        f"{len(st.signatures)} error signatures, {len(scan.failure_lines)} failure line(s).",
        duration_ms=_ms(started),
    )
    rule = classify_node(st)
    ctx.emit(
        state,
        "classify",
        "completed",
        f"Rule-based hint: {rule.category} (score {rule.score}, {rule.share:.0%} of signals).",
        detail={"scores": rule.scores, "supporting_lines": list(rule.supporting_lines)},
    )
    return {
        "signatures": [signature_to_json(s) for s in st.signatures],
        "document_count": st.document_count,
        "line_count": st.line_count,
        "log_tail": st.log_tail,
        "rule": rule_to_json(rule),
        "causes": causes_to_json(st.causes),
        "scan": scan_to_json(scan),
        "retrieval_round": 0,
        "llm_calls": 0,
        "diagnosis_attempt": 0,
        "attempt": None,
        "attempts": [],
        "best": None,
        "abstained": False,
        "proposals": [],
        "decision": None,
    }


def _targeted_items(
    session: Session, st: InvestigationState, lines: list[int]
) -> list[EvidenceItem]:
    """The smallest log chunk around each missing failure line."""
    items: dict[uuid.UUID, EvidenceItem] = {}
    for line in lines:
        row = session.execute(
            select(Chunk, Document.name)
            .join(Document, Document.id == Chunk.document_id)
            .where(
                Document.investigation_id == st.investigation_id,
                Document.workspace_id == st.workspace_id,
                Document.source_type == "log",
                Chunk.start_line <= line,
                Chunk.end_line >= line,
            )
            .order_by(Chunk.end_line - Chunk.start_line, Chunk.ordinal)
            .limit(1)
        ).first()
        if row is None or row[0].id in items:
            continue
        chunk, name = row
        items[chunk.id] = EvidenceItem(
            label="T",
            chunk_id=chunk.id,
            document_name=name,
            step_name=chunk.step_name,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            lines=evidence_lines(chunk.content),
            score=0.0,
            channels=("targeted",),
        )
    return list(items.values())


def retrieve_graph_node(ctx: RunContext, state: GraphState) -> dict[str, Any]:
    started = time.perf_counter()
    st = pipeline_state(state)
    round_ = state.get("retrieval_round", 0)
    budget = evidence_budget_chars(ctx.config.num_ctx)
    if round_ == 0:
        if ctx.embedder is not None and "vector" in st.channels:
            try:
                embedded = index_node(ctx.engine, st, ctx.embedder)
            except InferenceError as exc:
                # Degrade, don't fail: signature + full-text search still work.
                st.query_vector = None
                ctx.emit(
                    state,
                    "index",
                    "failed",
                    f"Embeddings unavailable ({exc.code}); using signature and full-text "
                    "search only.",
                    duration_ms=_ms(started),
                )
            else:
                ctx.emit(
                    state,
                    "index",
                    "completed",
                    f"Embedded {embedded} new chunk(s) with {ctx.embedder.model}; vector "
                    "search enabled.",
                    detail={"embedder": ctx.embedder.name, "embedded": embedded},
                    duration_ms=_ms(started),
                )
            started = time.perf_counter()
        with Session(ctx.engine) as session:
            retrieve_node(session, st, budget)
        summary = f"Selected {len(st.evidence)} evidence excerpts."
    else:
        missing = list(state.get("completeness", {}).get("missing_lines", []))
        with Session(ctx.engine) as session:
            added = _targeted_items(session, st, missing)
        known = {item.chunk_id for item in added}
        merged = fit_to_budget(added + [e for e in st.evidence if e.chunk_id not in known], budget)
        st.evidence = [replace(item, label=f"E{i + 1}") for i, item in enumerate(merged)]
        lines = ", ".join(f"L{n}" for n in missing)
        summary = (
            f"Targeted retrieval (round {round_}): added {len(added)} log excerpt(s) "
            f"covering {lines}."
        )
    ctx.emit(
        state,
        "retrieve",
        "completed",
        summary,
        detail={
            "evidence": [
                {"label": e.label, "lines": f"{e.start_line}-{e.end_line}", "channels": e.channels}
                for e in st.evidence
            ]
        },
        duration_ms=_ms(started),
    )
    return {"evidence": [evidence_to_json(e) for e in st.evidence], "retrieval_round": round_ + 1}


def assess_node(ctx: RunContext, state: GraphState) -> dict[str, Any]:
    st = pipeline_state(state)
    rule = st.rule or classify_node(st)
    result = assess(scan_from_json(state["scan"]), st.signatures, rule, st.evidence)
    if result.status == "no_failure_shown":
        summary = "The log does not show a failure; Kensa will not ask the model to guess"
    elif result.status == "missing_lines":
        summary = "The excerpts miss the failure line(s) " + ", ".join(
            f"L{n}" for n in result.missing_lines
        )
    else:
        summary = "The excerpts include the failure line(s) " + ", ".join(
            f"L{n}" for n in result.key_lines
        )
    ctx.emit(
        state,
        "assess_completeness",
        "completed" if result.status == "sufficient" else "info",
        summary + ".",
        detail=completeness_to_json(result),
    )
    return {"completeness": completeness_to_json(result)}


def route_completeness(ctx: RunContext, state: GraphState) -> str:
    status = state["completeness"]["status"]
    if status == "no_failure_shown":
        return "abstain"
    targeted_rounds = state.get("retrieval_round", 1) - 1
    if status == "missing_lines" and targeted_rounds < ctx.config.max_retrieval_rounds:
        return "retrieve"
    return "diagnose" if ctx.can_call_model(state) else "abstain"


def diagnose_graph_node(ctx: RunContext, state: GraphState) -> dict[str, Any]:
    started = time.perf_counter()
    st = pipeline_state(state)
    rule = st.rule or classify_node(st)
    number = state.get("diagnosis_attempt", 0) + 1
    messages = build_messages(
        st.title, rule, st.evidence, state["completeness"]["notes"], st.causes
    )
    previous = state.get("attempt")
    if previous and previous["result"] is not None and previous.get("verification"):
        messages = retry_messages(
            messages,
            json.dumps(previous["result"]["draft"]),
            previous["verification"]["feedback"],
        )
    request = StructuredRequest(
        task="diagnosis",
        schema=DiagnosisDraft,
        messages=messages,
        hints={"mock_response": rules_only_draft(st).model_dump()},
    )
    provider = ctx.provider
    target = f"{provider.name} ({provider.model})" if provider.model else "rules-only provider"
    ctx.emit(state, "diagnose", "started", f"Attempt {number}: asking {target} for a diagnosis.")
    result: StructuredResult[DiagnosisDraft] | None
    try:
        result = provider.generate_structured(request)
    except MalformedOutputError:
        result = None
        ctx.emit(state, "diagnose", "failed", "The reply did not match the schema after a repair.")
    except InferenceError as exc:
        ctx.emit(state, "diagnose", "failed", f"{exc.code}: {exc}", duration_ms=_ms(started))
        raise _job_error(exc) from exc
    else:
        ctx.emit(
            state,
            "diagnose",
            "completed",
            f'Proposed "{result.value.category}" with {len(result.value.citations)} citation(s).',
            detail={
                "provider": result.provider,
                "model": result.model,
                "prompt_tokens": result.prompt_tokens,
                "output_tokens": result.output_tokens,
                "attempts": result.attempts,
                "timings": dict(result.timings),
            },
            duration_ms=_ms(started),
        )
    attempt: Json = {
        "number": number,
        "result": result_to_json(result) if result else None,
        "malformed": result is None,
    }
    return {
        "attempt": attempt,
        "diagnosis_attempt": number,
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


def verify_graph_node(ctx: RunContext, state: GraphState) -> dict[str, Any]:
    st = pipeline_state(state)
    attempt = dict(state["attempt"] or {})
    if attempt.get("result") is None:
        verification = Verification(
            "not_established",
            "unknown",
            [],
            ["The model's reply did not match the required structure, even after a repair."],
            retryable=True,
            feedback=["Reply with JSON that matches the required structure."],
        )
    else:
        draft = result_from_json(attempt["result"]).value
        evidence = {item.label: item for item in st.evidence}
        verification = verify(draft, evidence, st.rule or classify_node(st), st.causes)
    attempt["verification"] = verification_to_json(verification)

    best = state.get("best")
    if (
        best is None
        or STATUS_RANK[verification.status] >= STATUS_RANK[best["verification"]["status"]]
    ):
        best = attempt
    history = list(state.get("attempts", []))
    digest = _digest(attempt["result"]["draft"]) if attempt.get("result") else None
    repeated = bool(history) and digest is not None and history[-1].get("digest") == digest
    if not verification.retryable:
        next_step = "accept"
    elif (
        attempt["number"] >= ctx.config.max_diagnosis_attempts
        or repeated
        or not ctx.can_call_model(state)
    ):
        next_step = "exhausted"
    else:
        next_step = "retry"
    history.append(
        {
            "number": attempt["number"],
            "status": verification.status,
            "category": verification.category,
            "valid": verification.valid_count,
            "total": len(verification.citations),
            "digest": digest,
        }
    )
    tail = {
        "accept": "",
        "retry": " Asking for a revised diagnosis.",
        "exhausted": " No retry left; reporting the best attempt.",
    }[next_step]
    ctx.emit(
        state,
        "verify",
        "completed",
        f"Attempt {attempt['number']}: {verification.valid_count}/{len(verification.citations)} "
        f"citations verified; status: {verification.status}.{tail}",
        detail={"status": verification.status, "notes": verification.notes, "next": next_step},
    )
    if next_step != "retry":
        # Deterministic first (D-044): a corroborated rule-based diagnosis replaces a final model
        # answer that is not corroborated.
        st.inference = result_from_json(best["result"]) if best.get("result") else None
        st.verification = verification_from_json(best["verification"])
        fallback = deterministic_fallback(st, ctx.provider)
        if fallback is not None and st.verification is not None:
            best = {
                "number": best.get("number", attempt["number"]),
                "result": result_to_json(fallback),
                "malformed": False,
                "verification": verification_to_json(st.verification),
                "deterministic": True,
            }
            ctx.emit(
                state,
                "verify",
                "info",
                f'Kensa\'s deterministic cause check corroborates "{st.verification.category}"; '
                "the model's answer was set aside.",
            )
    return {"attempt": attempt, "best": best, "attempts": history, "next_step": next_step}


def route_verification(state: GraphState) -> str:
    return "diagnose" if state.get("next_step") == "retry" else "plan_remediation"


def abstain_node(ctx: RunContext, state: GraphState) -> dict[str, Any]:
    completeness = state.get("completeness", {})
    if completeness.get("status") == "no_failure_shown":
        reason = completeness["notes"][0]
        uncertainty = " ".join(completeness["notes"][1:]) or (
            "The failing step's output, error message and exit status are not in the log."
        )
    else:
        reason = "The run's budget for model calls or time was used up before a diagnosis."
        uncertainty = "No diagnosis was attempted within the budget."
    draft = DiagnosisDraft(
        citations=[],
        root_cause=reason,
        summary="Cause not established: the evidence does not show the failure.",
        category="unknown",
        confidence=0.0,
        recommended_fixes=[
            "Retrieve the complete log of the failed job, including the failing step's output "
            "and exit status, then investigate again."
        ],
        uncertainty=uncertainty,
    )
    result = StructuredResult(draft, ctx.provider.name, None, None, None, 0, 0)
    verification = Verification(
        "not_established",
        "unknown",
        [],
        [*completeness.get("notes", []), "Kensa abstained without asking the model."],
    )
    ctx.emit(state, "abstain", "completed", f"Cause not established. {reason}")
    best: Json = {
        "number": 0,
        "result": result_to_json(result),
        "malformed": False,
        "verification": verification_to_json(verification),
    }
    return {"best": best, "abstained": True}


def _repository_files(
    session: Session, items: list[EvidenceItem]
) -> Mapping[uuid.UUID, RepositoryFile]:
    rows = session.execute(
        select(Document.id, Document.name, Document.content)
        .join(Chunk, Chunk.document_id == Document.id)
        .where(Chunk.id.in_([item.chunk_id for item in items]))
        .distinct()
    ).all()
    return {row.id: RepositoryFile(row.id, row.name, row.content) for row in rows}


def plan_node(ctx: RunContext, state: GraphState) -> dict[str, Any]:
    started = time.perf_counter()
    best = state.get("best")
    status = best["verification"]["status"] if best else "not_established"
    if best is None or best["result"] is None or status not in ("corroborated", "plausible"):
        reason = (
            "the evidence points to a different cause"
            if status == "conflicting"
            else "the cause is not established"
        )
        ctx.emit(state, "plan_remediation", "info", f"No remediation proposed: {reason}.")
        return {"proposals": []}

    st = pipeline_state(state)
    draft = result_from_json(best["result"]).value
    category = best["verification"]["category"]
    origin = "template" if ctx.provider.name == "mock" else "model"
    fixes = fix_proposals(draft.recommended_fixes, category, origin)
    edits: list[Proposal] = []
    dropped: list[str] = []
    llm_calls = state.get("llm_calls", 0)
    files = [e for e in st.evidence if e.source_type in REPOSITORY_SOURCES]
    if (
        ctx.config.remediation_diffs
        and ctx.provider.name != "mock"
        and files
        and ctx.can_call_model(state)
    ):
        request = StructuredRequest(
            task="remediation",
            schema=RemediationDraft,
            messages=build_planner_messages(
                category, draft.summary, draft.root_cause, draft.recommended_fixes, files
            ),
            hints={"mock_response": {"edits": [], "risks": [], "validation_steps": []}},
        )
        llm_calls += 1
        try:
            plan = ctx.provider.generate_structured(request)
        except MalformedOutputError:
            dropped.append("malformed_plan")
        except InferenceError as exc:
            ctx.emit(state, "plan_remediation", "failed", f"{exc.code}: {exc}")
            raise _job_error(exc) from exc
        else:
            with Session(ctx.engine) as session:
                repository = _repository_files(session, files)
            evidence = {item.label: item for item in st.evidence}
            for edit in plan.value.edits:
                outcome = validate_edit(
                    edit,
                    evidence,
                    repository,
                    risks=[*plan.value.risks, *CATEGORY_RISKS[category]],
                    validation_steps=[*plan.value.validation_steps, *CATEGORY_VALIDATION[category]],
                )
                if isinstance(outcome, str):
                    dropped.append(outcome)
                else:
                    edits.append(outcome)
    proposals = (edits + fixes)[:MAX_PROPOSALS]
    summary = (
        f"Proposed {len(proposals)} change(s) for human review "
        f"({len(edits)} with a diff checked against the file)."
    )
    if dropped:
        summary += f" Dropped {len(dropped)} model edit(s): {', '.join(dropped)}."
    ctx.emit(
        state,
        "plan_remediation",
        "completed",
        summary,
        detail={"proposals": len(proposals), "diffs": len(edits), "dropped": dropped},
        duration_ms=_ms(started),
    )
    return {"proposals": [p.to_dict() for p in proposals], "llm_calls": llm_calls}


def persist_node(ctx: RunContext, state: GraphState) -> dict[str, Any]:
    st = pipeline_state(state)
    verification = st.verification
    if verification is None:
        raise RuntimeError("persist_report reached without a diagnosis")
    proposals = [Proposal.from_dict(p) for p in state.get("proposals", [])]
    completeness = state.get("completeness")
    with fenced(ctx.engine, ctx.lease) as session:
        decided = session.scalar(
            select(ApprovalDecision.id).where(
                ApprovalDecision.investigation_id == st.investigation_id
            )
        )
        if decided is not None:
            # Re-run after a crash, but a human already decided on this report: keep it.
            return {}
        persist_report(
            session,
            st,
            ctx.provider,
            final_status="awaiting_approval" if proposals else "completed",
            evidence_complete=(
                None if completeness is None else completeness["status"] != "no_failure_shown"
            ),
            diagnosis_attempts=state.get("diagnosis_attempt", 0),
        )
        session.execute(
            delete(RemediationProposal).where(
                RemediationProposal.investigation_id == st.investigation_id
            )
        )
        session.add_all(
            RemediationProposal(
                workspace_id=st.workspace_id,
                investigation_id=st.investigation_id,
                ordinal=ordinal,
                title=p.title[:200],
                action=p.action,
                rationale=p.rationale,
                origin=p.origin,
                target_document_id=p.target_document_id,
                target_path=p.target_path,
                diff=p.diff,
                risks=list(p.risks),
                validation_steps=list(p.validation_steps),
                flags=list(p.flags),
            )
            for ordinal, p in enumerate(proposals, start=1)
        )
        waiting = (
            f" Waiting for a human decision on {len(proposals)} proposal(s)." if proposals else ""
        )
        append_event(
            session,
            workspace_id=st.workspace_id,
            investigation_id=st.investigation_id,
            attempt=ctx.lease.attempt,
            node="report",
            event_type="completed",
            summary=f"Report saved: {verification.category} ({verification.status}).{waiting}",
        )
    if (
        ctx.config.index_incidents
        and verification.status == "corroborated"
        and st.inference is not None
    ):
        index_incident(ctx.engine, st, ctx.embedder, Recorder(ctx.engine, ctx.lease, st))
    return {}


def route_after_persist(state: GraphState) -> str:
    return "approval" if state.get("proposals") else END


def approval_node(state: GraphState) -> dict[str, Any]:
    # No side effects before interrupt(): LangGraph re-runs this node from the top on resume.
    value = interrupt({"investigation_id": state["investigation_id"]})
    return {"decision": value if isinstance(value, dict) else {"decision": str(value)}}


def record_decision_node(ctx: RunContext, state: GraphState) -> dict[str, Any]:
    with Session(ctx.engine) as session:
        row = session.scalars(
            select(ApprovalDecision).where(
                ApprovalDecision.investigation_id == uuid.UUID(state["investigation_id"])
            )
        ).one_or_none()
    if row is None:
        raise PermanentJobError("invalid_job", "resumed without a recorded decision")
    if (state.get("decision") or {}).get("decision") != row.decision:
        raise PermanentJobError("invalid_job", "the resume value differs from the decision")
    count = len(state.get("proposals", []))
    if row.decision == "approved":
        summary = (
            f"Decision recorded: approved {count} proposal(s). Kensa does not apply changes; "
            "apply them yourself."
        )
    else:
        summary = f"Decision recorded: rejected {count} proposal(s). Nothing was changed."
    ctx.emit(state, "record_decision", "completed", summary)
    return {"decision": {"decision": row.decision, "note": row.note}}


def finalize_node(ctx: RunContext, state: GraphState) -> dict[str, Any]:
    with fenced(ctx.engine, ctx.lease) as session:
        investigation = session.get_one(Investigation, uuid.UUID(state["investigation_id"]))
        investigation.status = "completed"
        investigation.finished_at = func.now()
        investigation.error_code = None
        investigation.error_message = None
        append_event(
            session,
            workspace_id=investigation.workspace_id,
            investigation_id=investigation.id,
            attempt=ctx.lease.attempt,
            node="finalize",
            event_type="completed",
            summary="Investigation closed.",
        )
    return {}


# ---------------------------------------------------------------------------------- graph ---


def build_graph(ctx: RunContext) -> StateGraph[GraphState]:
    def bind(name: str, node: Callable[[RunContext, GraphState], dict[str, Any]]) -> Any:
        def run(state: GraphState) -> dict[str, Any]:
            with tracer.start_as_current_span(
                f"node.{name}", attributes={"kensa.investigation_id": state["investigation_id"]}
            ):
                return node(ctx, state)

        return run

    graph: StateGraph[GraphState] = StateGraph(GraphState)
    graph.add_node("collect_evidence", bind("collect_evidence", collect_node))
    graph.add_node("retrieve", bind("retrieve", retrieve_graph_node))
    graph.add_node("assess_completeness", bind("assess_completeness", assess_node))
    graph.add_node("diagnose", bind("diagnose", diagnose_graph_node))
    graph.add_node("verify", bind("verify", verify_graph_node))
    graph.add_node("abstain", bind("abstain", abstain_node))
    graph.add_node("plan_remediation", bind("plan_remediation", plan_node))
    graph.add_node("persist_report", bind("persist_report", persist_node))
    graph.add_node("approval", approval_node)
    graph.add_node("record_decision", bind("record_decision", record_decision_node))
    graph.add_node("finalize", bind("finalize", finalize_node))

    graph.add_edge(START, "collect_evidence")
    graph.add_edge("collect_evidence", "retrieve")
    graph.add_edge("retrieve", "assess_completeness")
    graph.add_conditional_edges(
        "assess_completeness",
        lambda state: route_completeness(ctx, state),
        ["abstain", "retrieve", "diagnose"],
    )
    graph.add_edge("diagnose", "verify")
    graph.add_conditional_edges("verify", route_verification, ["diagnose", "plan_remediation"])
    graph.add_edge("abstain", "persist_report")
    graph.add_edge("plan_remediation", "persist_report")
    graph.add_conditional_edges("persist_report", route_after_persist, ["approval", END])
    graph.add_edge("approval", "record_decision")
    graph.add_edge("record_decision", "finalize")
    graph.add_edge("finalize", END)
    return graph


# --------------------------------------------------------------------------------- runner ---

DriveAction = Literal["start", "resume", "decide", "wait", "done"]


def _decision(engine: Engine, investigation_id: uuid.UUID) -> str | None:
    with Session(engine) as session:
        return session.scalar(
            select(ApprovalDecision.decision).where(
                ApprovalDecision.investigation_id == investigation_id
            )
        )


def _set_status(engine: Engine, lease: Lease, investigation_id: uuid.UUID, status: str) -> None:
    with fenced(engine, lease) as session:
        investigation = session.get_one(Investigation, investigation_id)
        if investigation.status != status:
            investigation.status = status
            if status == "completed":
                investigation.finished_at = investigation.finished_at or func.now()


@traced("investigation.run")
def run_agent(
    lease: Lease,
    engine: Engine,
    provider: InferenceProvider,
    *,
    database_url: str,
    config: AgentConfig,
    embedder: Embedder | None = None,
) -> GraphState | None:
    """Drive the investigation's graph as far as it can go: start it, resume it from its last
    checkpoint after a crash, or resume it past the approval interrupt once a decision exists.
    Returns the final graph state (None if nothing ran)."""
    disable_tracing()
    if lease.investigation_id is None:
        raise PermanentJobError("invalid_job", "investigate job without an investigation")
    investigation_id = lease.investigation_id
    with Session(engine) as session:
        investigation = session.get_one(Investigation, investigation_id)
        initial: GraphState = {
            "investigation_id": str(investigation.id),
            "workspace_id": str(investigation.workspace_id),
            "title": investigation.title,
            "repository_id": str(investigation.repository_id)
            if investigation.repository_id
            else None,
            "channels": sorted(config.channels),
        }
    ctx = RunContext(engine, lease, provider, embedder, config)
    run_config: RunnableConfig = {
        "configurable": {"thread_id": thread_id(investigation_id)},
        "recursion_limit": RECURSION_LIMIT,
    }
    with open_checkpointer(database_url, lease_fence(engine, lease)) as saver:
        app: CompiledStateGraph[GraphState] = build_graph(ctx).compile(checkpointer=saver)
        for _ in range(MAX_DRIVE_ROUNDS):
            snapshot = app.get_state(run_config)
            payload: GraphState | Command[Any] | None
            if not snapshot.values:
                payload, summary = initial, f"Attempt {lease.attempt} of {lease.max_attempts}."
            elif not snapshot.next:
                # Finished earlier (for example the worker died after the last step).
                _set_status(engine, lease, investigation_id, "completed")
                break
            elif snapshot.interrupts:
                decision = _decision(engine, investigation_id)
                if decision is None:
                    _set_status(engine, lease, investigation_id, "awaiting_approval")
                    break
                payload = Command(resume={"decision": decision})
                summary = f"Resuming after the operator's decision ({decision})."
            else:
                payload = None
                summary = (
                    f"Attempt {lease.attempt} of {lease.max_attempts}: resuming from the last "
                    f"checkpoint (next step: {', '.join(snapshot.next)})."
                )
            with fenced(engine, lease) as session:
                investigation = session.get_one(Investigation, investigation_id)
                investigation.status = "running"
                investigation.started_at = investigation.started_at or func.now()
                append_event(
                    session,
                    workspace_id=investigation.workspace_id,
                    investigation_id=investigation_id,
                    attempt=lease.attempt,
                    node="pipeline",
                    event_type="started",
                    summary=summary,
                )
            app.invoke(payload, run_config, durability="sync")
        final = app.get_state(run_config)
        return cast(GraphState, final.values) if final.values else None
