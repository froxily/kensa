"""The M1 investigation pipeline: collect → classify → retrieve → diagnose → verify → report.

Nodes are plain functions over ``InvestigationState``; the M3 agent graph
(``kensa.agents.graph``) wraps them as LangGraph nodes. ``run_investigation`` remains as the
linear M1/M2 runner, which the evaluation harness uses for its M2 baselines.

Every write happens in a ``fenced`` transaction that first re-checks the job lease (D-006), and
the report step *replaces* earlier results, so re-running an investigation after a crash never
duplicates evidence or diagnoses.
"""

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import Any

from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from kensa.agents.evidence import EvidenceItem, evidence_lines
from kensa.agents.fixes import FIX_TEMPLATES
from kensa.agents.prompts import build_messages, evidence_budget_chars, fit_to_budget
from kensa.agents.schemas import CitationDraft, DiagnosisDraft
from kensa.agents.verifier import Verification, verify
from kensa.analysis.categories import CATEGORIES, CATEGORY_DESCRIPTIONS
from kensa.analysis.causes import CauseEvidence, assess_causes
from kensa.analysis.classifier import RuleClassification, classify
from kensa.analysis.signatures import SignatureMatch
from kensa.db.models import (
    AgentEvent,
    Citation,
    Diagnosis,
    Document,
    ErrorSignature,
    Evidence,
    Investigation,
)
from kensa.indexing.service import embed_pending, upsert_document
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
from kensa.retrieval.search import ALL_CHANNELS, retrieve, vector_query_text

# The model's self-reported confidence is capped by what verification could establish. It is
# kept for analysis only; the UI shows the evidence-based status instead (D-040).
CONFIDENCE_CAPS = {
    "corroborated": 0.9,
    "plausible": 0.6,
    "conflicting": 0.3,
    "not_established": 0.1,
}


@dataclass
class InvestigationState:
    investigation_id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    signatures: list[SignatureMatch] = field(default_factory=list)
    document_count: int = 0
    line_count: int = 0
    rule: RuleClassification | None = None
    evidence: list[EvidenceItem] = field(default_factory=list)
    inference: StructuredResult[DiagnosisDraft] | None = None
    malformed: bool = False
    verification: Verification | None = None
    repository_id: uuid.UUID | None = None
    log_tail: list[str] = field(default_factory=list)
    query_vector: list[float] | None = None
    channels: frozenset[str] = ALL_CHANNELS
    # M5.1: statements of an underlying cause anywhere in the log (D-041).
    causes: CauseEvidence = field(default_factory=CauseEvidence)


@contextmanager
def fenced(engine: Engine, lease: Lease | None) -> Iterator[Session]:
    """A write transaction that only commits while ``lease`` is still held."""
    with Session(engine) as session, session.begin():
        if lease is not None:
            queue.assert_lease(session, lease)
        yield session


def append_event(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    investigation_id: uuid.UUID,
    attempt: int,
    node: str,
    event_type: str,
    summary: str,
    detail: dict[str, Any] | None = None,
    duration_ms: int | None = None,
) -> None:
    # Lock the investigation so the worker and the outcome listener allocate distinct seqs.
    session.execute(
        select(Investigation.id).where(Investigation.id == investigation_id).with_for_update()
    )
    last = session.scalar(
        select(func.coalesce(func.max(AgentEvent.seq), 0)).where(
            AgentEvent.investigation_id == investigation_id
        )
    )
    session.add(
        AgentEvent(
            workspace_id=workspace_id,
            investigation_id=investigation_id,
            seq=(last or 0) + 1,
            attempt=attempt,
            node=node,
            event_type=event_type,
            summary=summary[:500],
            detail=detail or {},
            duration_ms=duration_ms,
        )
    )


class Recorder:
    def __init__(self, engine: Engine, lease: Lease, state: InvestigationState) -> None:
        self.engine, self.lease, self.state = engine, lease, state

    def emit(
        self,
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
                workspace_id=self.state.workspace_id,
                investigation_id=self.state.investigation_id,
                attempt=self.lease.attempt,
                node=node,
                event_type=event_type,
                summary=summary,
                detail=detail,
                duration_ms=duration_ms,
            )


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


# ---------------------------------------------------------------------------------- nodes ---


def collect_evidence(session: Session, state: InvestigationState) -> None:
    documents = session.execute(
        select(Document.id, Document.line_count).where(
            Document.investigation_id == state.investigation_id,
            Document.workspace_id == state.workspace_id,
        )
    ).all()
    state.document_count = len(documents)
    state.line_count = sum(d.line_count for d in documents)
    if documents:
        last_log = session.scalar(select(Document.content).where(Document.id == documents[0].id))
        state.log_tail = (last_log or "").split("\n")[-20:]
    log = session.scalar(
        select(Document.content)
        .where(
            Document.investigation_id == state.investigation_id,
            Document.workspace_id == state.workspace_id,
            Document.source_type == "log",
        )
        .order_by(Document.created_at)
        .limit(1)
    )
    state.causes = assess_causes(log.split("\n")) if log else CauseEvidence()
    rows = session.scalars(
        select(ErrorSignature)
        .where(ErrorSignature.document_id.in_([d.id for d in documents]))
        .order_by(ErrorSignature.line_number, ErrorSignature.rule_id)
    ).all()
    state.signatures = [
        SignatureMatch(
            line_number=r.line_number,
            rule_id=r.rule_id,
            kind=r.kind,
            value=r.value,
            category=r.category_hint if r.category_hint in CATEGORIES else None,
            weight=r.weight,
            excerpt=r.excerpt,
        )
        for r in rows
    ]


def classify_node(state: InvestigationState) -> RuleClassification:
    state.rule = classify(state.signatures, state.causes)
    return state.rule


def index_node(engine: Engine, state: InvestigationState, embedder: Embedder) -> int:
    """Embed not-yet-embedded chunks in this investigation's scope, then the query.
    Runs before diagnosis, never concurrently with LLM inference (owner instruction)."""
    with Session(engine) as session, session.begin():
        scope = select(Document.id).where(
            Document.workspace_id == state.workspace_id,
            (Document.investigation_id == state.investigation_id)
            | (
                Document.investigation_id.is_(None)
                & (
                    (Document.repository_id == state.repository_id)
                    | (
                        Document.repository_id.is_(None)
                        & Document.source_type.in_(("kb", "incident"))
                    )
                )
            ),
        )
        count = embed_pending(session, embedder, state.workspace_id, list(session.scalars(scope)))
    query = vector_query_text(state.title, state.signatures, state.log_tail)
    state.query_vector = embedder.embed_query(query)
    return count


def retrieve_node(session: Session, state: InvestigationState, budget_chars: int) -> None:
    chunks = retrieve(
        session,
        workspace_id=state.workspace_id,
        investigation_id=state.investigation_id,
        signatures=state.signatures,
        repository_id=state.repository_id,
        query_vector=state.query_vector,
        channels=state.channels,
    )
    items = [
        EvidenceItem(
            label=f"E{index + 1}",
            chunk_id=c.chunk_id,
            document_name=c.document_name,
            step_name=c.step_name,
            start_line=c.start_line,
            end_line=c.end_line,
            lines=evidence_lines(c.content),
            score=c.score,
            channels=c.channels,
            source_type=c.source_type,
        )
        for index, c in enumerate(chunks)
    ]
    kept = fit_to_budget(items, budget_chars)
    state.evidence = [replace(item, label=f"E{i + 1}") for i, item in enumerate(kept)]


def rules_only_draft(state: InvestigationState) -> DiagnosisDraft:
    """The deterministic diagnosis the mock provider returns (and a CI-safe baseline)."""
    rule = state.rule or classify([])
    citations: list[CitationDraft] = []
    for line in rule.supporting_lines:
        # Signature lines are log lines: never match them against repository files.
        for item in (e for e in state.evidence if e.source_type == "log"):
            text = item.line(line)
            if text is not None and text.strip():
                quote = text.strip()[:200]
                citations.append(CitationDraft(evidence_id=item.label, line=line, quote=quote))
                break
        if len(citations) == 3:
            break
    if rule.category == "unknown" or not citations:
        return DiagnosisDraft(
            citations=[],
            root_cause="No known failure pattern matched the log.",
            summary="Rules-only analysis could not identify the failure.",
            category="unknown",
            confidence=0.0,
            recommended_fixes=FIX_TEMPLATES["unknown"],
            uncertainty="Deterministic rules only; no language model was used.",
        )
    # The category may rest on a stated cause alone (M5.1), with no signature of its own.
    top = min(
        (s for s in state.signatures if s.category == rule.category),
        key=lambda s: (-s.weight, s.line_number),
        default=None,
    )
    strongest = top.excerpt[:300] if top is not None else citations[0].quote
    return DiagnosisDraft(
        citations=citations,
        root_cause=f"Signature rules matched {len(rule.supporting_lines)} line(s) indicating "
        f"that {CATEGORY_DESCRIPTIONS[rule.category]}. Strongest signal: {strongest}",
        summary=f"Rules-only analysis: {CATEGORY_DESCRIPTIONS[rule.category]}.",
        category=rule.category,
        confidence=round(0.5 + 0.4 * rule.share, 2) if rule.is_strong else 0.4,
        recommended_fixes=FIX_TEMPLATES[rule.category],
        uncertainty="Deterministic rules only; no language model was used. They identify the "
        "failing signal, not necessarily the change that introduced it.",
    )


def diagnose_node(state: InvestigationState, provider: InferenceProvider) -> None:
    rule = state.rule or classify([])
    request = StructuredRequest(
        task="diagnosis",
        schema=DiagnosisDraft,
        messages=build_messages(state.title, rule, state.evidence, causes=state.causes),
        hints={"mock_response": rules_only_draft(state).model_dump()},
    )
    try:
        state.inference = provider.generate_structured(request)
    except MalformedOutputError:
        state.malformed = True


def verify_node(state: InvestigationState) -> Verification:
    if state.inference is None:
        state.verification = Verification(
            "not_established",
            "unknown",
            [],
            ["The model's reply did not match the required structure, even after a repair."],
        )
    else:
        evidence = {item.label: item for item in state.evidence}
        state.verification = verify(
            state.inference.value, evidence, state.rule or classify([]), state.causes
        )
    return state.verification


def deterministic_fallback(
    state: InvestigationState, provider: InferenceProvider
) -> StructuredResult[DiagnosisDraft] | None:
    """Deterministic first (D-044). When the model established no cause, or named a different one,
    and Kensa's rule-based diagnosis is corroborated (its cause check finds the cause stated in
    the log, cited, and uncontested), report the rule-based diagnosis and say that the model's
    answer was set aside. Updates ``state`` and returns the replacement result, or returns None
    and changes nothing."""
    current = state.verification
    if current is None or current.status == "corroborated":
        return None
    draft = rules_only_draft(state)
    if draft.category in ("unknown", current.category):
        return None  # nothing to offer, or the model named the same cause: keep its own answer
    evidence = {item.label: item for item in state.evidence}
    checked = verify(draft, evidence, state.rule or classify([]), state.causes)
    if checked.status != "corroborated":
        return None
    model_answer = state.inference.value.category if state.inference else "no valid reply"
    note = (
        "Reported from Kensa's deterministic cause check, not from the model: the log states "
        f'this cause and no competing one. The model\'s answer ("{model_answer}", '
        f"{current.status}) was set aside."
    )
    if state.inference is not None:
        result = replace(state.inference, value=draft)
    else:
        result = StructuredResult(draft, provider.name, provider.model, None, None, 0, 0)
    state.inference = result
    state.verification = replace(checked, notes=[*checked.notes, note])
    return result


class InvariantError(RuntimeError):
    """A report would break a guarantee Kensa makes; it is never persisted."""


def persist_report(
    session: Session,
    state: InvestigationState,
    provider: InferenceProvider,
    *,
    final_status: str = "completed",
    evidence_complete: bool | None = None,
    diagnosis_attempts: int = 1,
) -> Diagnosis:
    verification = state.verification
    if verification is None:
        raise RuntimeError("persist_report called before verification")
    # An invalid citation can never be part of a corroborated diagnosis (M3 guarantee, D-040).
    if verification.status == "corroborated" and not all(c.valid for c in verification.citations):
        raise InvariantError("a corroborated diagnosis must not contain a rejected citation")
    rule = state.rule or classify([])
    session.execute(delete(Evidence).where(Evidence.investigation_id == state.investigation_id))
    session.execute(delete(Diagnosis).where(Diagnosis.investigation_id == state.investigation_id))
    session.add_all(
        Evidence(
            workspace_id=state.workspace_id,
            investigation_id=state.investigation_id,
            chunk_id=item.chunk_id,
            label=item.label,
            rank=rank,
            score=item.score,
            channels=list(item.channels),
        )
        for rank, item in enumerate(state.evidence, start=1)
    )
    result = state.inference
    draft = result.value if result else None
    diagnosis = Diagnosis(
        workspace_id=state.workspace_id,
        investigation_id=state.investigation_id,
        category=verification.category,
        rule_category=rule.category,
        summary=draft.summary if draft else "No diagnosis: the model's reply was invalid.",
        root_cause=draft.root_cause if draft else "",
        confidence=min(draft.confidence if draft else 0.0, CONFIDENCE_CAPS[verification.status]),
        uncertainty=draft.uncertainty if draft else "",
        recommended_fixes=list(draft.recommended_fixes) if draft else FIX_TEMPLATES["unknown"],
        verification_status=verification.status,
        verification_notes=verification.notes,
        provider=provider.name,
        model=provider.model,
        prompt_tokens=result.prompt_tokens if result else None,
        output_tokens=result.output_tokens if result else None,
        duration_ms=result.duration_ms if result else None,
        evidence_complete=evidence_complete,
        diagnosis_attempts=diagnosis_attempts,
    )
    session.add(diagnosis)
    session.flush()
    session.add_all(
        Citation(
            workspace_id=state.workspace_id,
            diagnosis_id=diagnosis.id,
            ordinal=c.ordinal,
            evidence_label=c.evidence_label,
            chunk_id=c.chunk_id,
            line_number=c.line,
            quote=c.quote,
            valid=c.valid,
            rejection_reason=c.reason,
        )
        for c in verification.citations
    )
    investigation = session.get_one(Investigation, state.investigation_id)
    investigation.status = final_status
    investigation.finished_at = func.now() if final_status == "completed" else None
    investigation.error_code = None
    investigation.error_message = None
    return diagnosis


# --------------------------------------------------------------------------------- runner ---


def run_investigation(
    lease: Lease,
    engine: Engine,
    provider: InferenceProvider,
    *,
    num_ctx: int,
    embedder: Embedder | None = None,
    channels: frozenset[str] = ALL_CHANNELS,
    index_incidents: bool = False,
) -> InvestigationState:
    if lease.investigation_id is None:
        raise PermanentJobError("invalid_job", "investigate job without an investigation")
    with Session(engine) as session:
        investigation = session.get_one(Investigation, lease.investigation_id)
        state = InvestigationState(
            lease.investigation_id, investigation.workspace_id, investigation.title
        )
        state.repository_id = investigation.repository_id
        state.channels = channels
    recorder = Recorder(engine, lease, state)

    with fenced(engine, lease) as session:
        investigation = session.get_one(Investigation, state.investigation_id)
        investigation.status = "running"
        investigation.started_at = investigation.started_at or func.now()
    recorder.emit("pipeline", "started", f"Attempt {lease.attempt} of {lease.max_attempts}.")

    started = time.perf_counter()
    with Session(engine) as session:
        collect_evidence(session, state)
    recorder.emit(
        "collect_evidence",
        "completed",
        f"{state.document_count} log, {state.line_count} lines, "
        f"{len(state.signatures)} error signatures.",
        duration_ms=_ms(started),
    )

    started = time.perf_counter()
    rule = classify_node(state)
    recorder.emit(
        "classify",
        "completed",
        f"Rule-based hint: {rule.category} (score {rule.score}, {rule.share:.0%} of signals).",
        detail={"scores": rule.scores, "supporting_lines": list(rule.supporting_lines)},
        duration_ms=_ms(started),
    )

    if embedder is not None and "vector" in channels:
        started = time.perf_counter()
        try:
            embedded = index_node(engine, state, embedder)
        except InferenceError as exc:
            # Degrade, don't fail: signature + full-text search still work without embeddings.
            state.query_vector = None
            recorder.emit(
                "index",
                "failed",
                f"Embeddings unavailable ({exc.code}); using signature and full-text search only.",
                duration_ms=_ms(started),
            )
        else:
            recorder.emit(
                "index",
                "completed",
                f"Embedded {embedded} new chunk(s) with {embedder.model}; vector search enabled.",
                detail={"embedder": embedder.name, "model": embedder.model, "embedded": embedded},
                duration_ms=_ms(started),
            )

    started = time.perf_counter()
    with Session(engine) as session:
        retrieve_node(session, state, evidence_budget_chars(num_ctx))
    recorder.emit(
        "retrieve",
        "completed",
        f"Selected {len(state.evidence)} evidence excerpts.",
        detail={
            "evidence": [
                {"label": e.label, "lines": f"{e.start_line}-{e.end_line}", "channels": e.channels}
                for e in state.evidence
            ]
        },
        duration_ms=_ms(started),
    )

    started = time.perf_counter()
    target = f"{provider.name} ({provider.model})" if provider.model else "rules-only provider"
    recorder.emit("diagnose", "started", f"Requesting a structured diagnosis from {target}.")
    try:
        diagnose_node(state, provider)
    except InferenceError as exc:
        recorder.emit("diagnose", "failed", f"{exc.code}: {exc}", duration_ms=_ms(started))
        error_type = RetryableJobError if exc.retryable else PermanentJobError
        raise error_type(exc.code, str(exc)) from exc
    if state.inference is None:
        recorder.emit("diagnose", "failed", "The reply did not match the schema after a repair.")
    else:
        result = state.inference
        recorder.emit(
            "diagnose",
            "completed",
            f'Proposed "{result.value.category}" with {len(result.value.citations)} citation(s).',
            detail={
                "provider": result.provider,
                "model": result.model,
                "prompt_tokens": result.prompt_tokens,
                "output_tokens": result.output_tokens,
                "attempts": result.attempts,
            },
            duration_ms=_ms(started),
        )

    started = time.perf_counter()
    verification = verify_node(state)
    recorder.emit(
        "verify",
        "completed",
        f"{verification.valid_count}/{len(verification.citations)} citations verified; "
        f"status: {verification.status}.",
        detail={"status": verification.status, "notes": verification.notes},
        duration_ms=_ms(started),
    )
    if deterministic_fallback(state, provider) is not None:
        recorder.emit(
            "verify",
            "info",
            f"Kensa's deterministic cause check corroborates "
            f'"{state.verification.category if state.verification else "unknown"}"; '
            "the model's answer was set aside.",
        )

    with fenced(engine, lease) as session:
        persist_report(session, state, provider)
        append_event(
            session,
            workspace_id=state.workspace_id,
            investigation_id=state.investigation_id,
            attempt=lease.attempt,
            node="report",
            event_type="completed",
            summary=f"Report saved: {verification.category} ({verification.status}).",
        )

    if index_incidents and verification.status == "corroborated" and state.inference is not None:
        index_incident(engine, state, embedder, recorder)
    return state


def incident_markdown(state: InvestigationState) -> str:
    draft = state.inference.value if state.inference else None
    if draft is None or state.verification is None:
        return ""
    fixes = "\n".join(f"- {fix}" for fix in draft.recommended_fixes)
    return (
        f"# Incident: {state.title}\n\nCategory: {state.verification.category}\n\n"
        f"## Summary\n{draft.summary}\n\n## Root cause\n{draft.root_cause}\n\n## Fixes\n{fixes}\n"
    )


def index_incident(
    engine: Engine, state: InvestigationState, embedder: Embedder | None, recorder: Recorder
) -> None:
    """Make a verified investigation retrievable for later runs. Best effort: a failure here
    never changes the investigation's outcome."""
    try:
        with Session(engine) as session, session.begin():
            _, document_id = upsert_document(
                session,
                workspace_id=state.workspace_id,
                repository_id=None,
                source_type="incident",
                name=f"incident/{state.investigation_id}",
                content=incident_markdown(state),
            )
            if embedder is not None and document_id is not None:
                embed_pending(session, embedder, state.workspace_id, [document_id])
    except InferenceError as exc:
        recorder.emit("index", "info", f"Incident stored without embedding ({exc.code}).")
        return
    recorder.emit("index", "completed", "Verified incident added to the knowledge base.")
