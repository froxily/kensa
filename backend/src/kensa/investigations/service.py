"""Creating and retrying investigations. Each operation is one transaction: the investigation,
its redacted document, chunks, signatures and job are written together or not at all."""

import hashlib
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from kensa.agents.pipeline import append_event
from kensa.analysis.causes import assess_causes
from kensa.analysis.classifier import classify
from kensa.analysis.signatures import extract_signatures
from kensa.db.models import (
    ApprovalDecision,
    Chunk,
    Document,
    ErrorSignature,
    Investigation,
    Job,
    RemediationProposal,
    Repository,
    WorkflowRun,
)
from kensa.github.importer import GitHubImport
from kensa.indexing.service import ensure_repository, upsert_document
from kensa.ingestion.chunking import chunk_log
from kensa.ingestion.normalize import normalize_log
from kensa.ingestion.redaction import redact
from kensa.jobs import queue

INVESTIGATE_JOB = "investigate"
RESUME_JOB = "resume"


class InvestigationStateError(Exception):
    """The requested transition is not allowed in the investigation's current state."""


class DecisionConflictError(InvestigationStateError):
    """A different decision was already recorded for this investigation."""


@dataclass(frozen=True)
class NewInvestigation:
    title: str | None
    source: Literal["paste", "upload", "sample", "github"]
    provider: Literal["ollama", "mock"]
    document_name: str
    log_text: str
    repository_id: uuid.UUID | None = None


def _default_title(signature_excerpts: list[str], document_name: str) -> str:
    for excerpt in signature_excerpts:
        text = excerpt.removeprefix("##[error]").strip()
        if text:
            return text[:200]
    return document_name[:200]


def create_investigation(
    session: Session, workspace_id: uuid.UUID, new: NewInvestigation, model: str | None
) -> Investigation:
    """Raises ``LogRejectedError`` for unusable input and ``InvestigationStateError`` for a
    repository outside the workspace (nothing is written in either case)."""
    if new.repository_id is not None:
        owned = session.scalar(
            select(Repository.id).where(
                Repository.id == new.repository_id, Repository.workspace_id == workspace_id
            )
        )
        if owned is None:
            raise InvestigationStateError("repository not found")
    normalized = normalize_log(new.log_text)
    redaction = redact(normalized.text)
    lines = redaction.text.split("\n")
    if len(lines) != normalized.line_count:  # redaction must never move line numbers
        raise AssertionError("redaction changed the line count")

    signatures = extract_signatures(lines)
    rule = classify(signatures, assess_causes(lines))
    title = (new.title or "").strip()[:200] or _default_title(
        [s.excerpt for s in sorted(signatures, key=lambda s: (-s.weight, s.line_number))],
        new.document_name,
    )
    investigation = Investigation(
        workspace_id=workspace_id,
        repository_id=new.repository_id,
        title=title,
        source=new.source,
        status="queued",
        provider=new.provider,
        model=model if new.provider == "ollama" else None,
        rule_category=rule.category,
    )
    session.add(investigation)
    session.flush()

    content_bytes = redaction.text.encode("utf-8")
    document = Document(
        workspace_id=workspace_id,
        investigation_id=investigation.id,
        source_type="log",
        name=new.document_name[:255] or "log.txt",
        content=redaction.text,
        content_hash=hashlib.sha256(content_bytes).hexdigest(),
        byte_size=len(content_bytes),
        line_count=len(lines),
        redaction_count=redaction.total,
    )
    session.add(document)
    session.flush()

    drafts = chunk_log(lines, [s.line_number for s in signatures])
    chunks = [
        Chunk(
            workspace_id=workspace_id,
            document_id=document.id,
            ordinal=d.ordinal,
            kind=d.kind,
            step_name=d.step_name,
            start_line=d.start_line,
            end_line=d.end_line,
            content=d.content,
            content_hash=d.content_hash,
        )
        for d in drafts
    ]
    session.add_all(chunks)
    session.flush()

    # Point each signature at the error window around it (falling back to its step chunk).
    windows = [c for c in chunks if c.kind == "error_window"]
    steps = [c for c in chunks if c.kind == "step"]

    def chunk_for(line: int) -> uuid.UUID | None:
        for group in (windows, steps):
            for chunk in group:
                if chunk.start_line <= line <= chunk.end_line:
                    return chunk.id
        return None

    session.add_all(
        ErrorSignature(
            workspace_id=workspace_id,
            document_id=document.id,
            chunk_id=chunk_for(s.line_number),
            line_number=s.line_number,
            rule_id=s.rule_id,
            kind=s.kind,
            value=s.value,
            category_hint=s.category,
            weight=s.weight,
            excerpt=s.excerpt,
        )
        for s in signatures
    )
    queue.enqueue(
        session,
        workspace_id=workspace_id,
        kind=INVESTIGATE_JOB,
        idempotency_key=f"{INVESTIGATE_JOB}:{investigation.id}:1",
        investigation_id=investigation.id,
    )
    return investigation


def retry_investigation(
    session: Session, workspace_id: uuid.UUID, investigation_id: uuid.UUID
) -> Investigation | None:
    """Re-run a failed investigation. Returns None if it does not exist in this workspace."""
    investigation = session.execute(
        select(Investigation)
        .where(Investigation.id == investigation_id, Investigation.workspace_id == workspace_id)
        .with_for_update()
    ).scalar_one_or_none()
    if investigation is None:
        return None
    if investigation.status != "failed":
        raise InvestigationStateError(f"cannot retry: investigation is {investigation.status}")
    runs = session.scalar(
        select(func.count()).select_from(Job).where(Job.investigation_id == investigation.id)
    )
    investigation.status = "queued"
    investigation.error_code = None
    investigation.error_message = None
    investigation.finished_at = None
    queue.enqueue(
        session,
        workspace_id=workspace_id,
        kind=INVESTIGATE_JOB,
        idempotency_key=f"{INVESTIGATE_JOB}:{investigation.id}:{(runs or 0) + 1}",
        investigation_id=investigation.id,
    )
    return investigation


@dataclass(frozen=True)
class DecisionRecord:
    investigation: Investigation
    decision: ApprovalDecision
    created: bool


def decide(
    session: Session,
    workspace_id: uuid.UUID,
    investigation_id: uuid.UUID,
    decision: Literal["approved", "rejected"],
    note: str | None = None,
) -> DecisionRecord | None:
    """Record the operator's decision on an investigation's remediation proposals and queue
    the resume of its paused agent run, in one transaction.

    Idempotent: repeating the decision that is already recorded returns it unchanged (no second
    decision, no second resume job). A different decision raises ``DecisionConflictError``.
    Approving only records the decision; Kensa never applies a proposal.
    Returns None if the investigation does not exist in this workspace.
    """
    investigation = session.execute(
        select(Investigation)
        .where(Investigation.id == investigation_id, Investigation.workspace_id == workspace_id)
        .with_for_update()
    ).scalar_one_or_none()
    if investigation is None:
        return None
    existing = session.scalars(
        select(ApprovalDecision).where(ApprovalDecision.investigation_id == investigation.id)
    ).one_or_none()
    if existing is not None:
        if existing.decision != decision:
            raise DecisionConflictError(
                f"A different decision ({existing.decision}) was already recorded."
            )
        return DecisionRecord(investigation, existing, created=False)
    if investigation.status != "awaiting_approval":
        raise InvestigationStateError(
            f"cannot decide: investigation is {investigation.status}, not awaiting approval"
        )
    updated = session.execute(
        update(RemediationProposal)
        .where(
            RemediationProposal.investigation_id == investigation.id,
            RemediationProposal.status == "proposed",
        )
        .values(status=decision, decided_at=func.now())
    )
    if not updated.rowcount:  # type: ignore[attr-defined]
        raise InvestigationStateError("cannot decide: there are no proposals awaiting a decision")
    record = ApprovalDecision(
        workspace_id=workspace_id,
        investigation_id=investigation.id,
        decision=decision,
        note=(note or "").strip()[:1000] or None,
    )
    session.add(record)
    investigation.status = "queued"
    # One resume per decision. If a job for this investigation is still active (a worker
    # recovering from a crash), it picks the decision up itself (kensa.agents.graph.run_agent).
    queue.enqueue(
        session,
        workspace_id=workspace_id,
        kind=RESUME_JOB,
        idempotency_key=f"{RESUME_JOB}:{investigation.id}",
        investigation_id=investigation.id,
    )
    session.flush()
    return DecisionRecord(investigation, record, created=True)


def create_github_investigation(
    session: Session,
    workspace_id: uuid.UUID,
    imported: GitHubImport,
    provider: Literal["ollama", "mock"],
    model: str | None,
) -> Investigation:
    """Store a GitHub import: the repository snapshot at the run's commit (D-033), its files,
    the investigation with the job's log, and the run record. One transaction; the network part
    happened before (``kensa.github.importer.import_run``)."""
    run, job, repo = imported.run, imported.job, imported.repo
    snapshot = ensure_repository(
        session,
        workspace_id,
        f"{repo.owner}/{repo.repo}",
        provider="github",
        commit_sha=run.head_sha,
    )
    for file in imported.files:
        upsert_document(
            session,
            workspace_id=workspace_id,
            repository_id=snapshot.id,
            source_type=file.source_type,
            name=file.path,
            content=file.content,
        )
    new = NewInvestigation(
        title=None,
        source="github",
        provider=provider,
        document_name=f"{job.name}.log"[:255],
        log_text=imported.log_text,
        repository_id=snapshot.id,
    )
    investigation = create_investigation(session, workspace_id, new, model)
    session.add(
        WorkflowRun(
            workspace_id=workspace_id,
            investigation_id=investigation.id,
            repository_id=snapshot.id,
            owner=repo.owner,
            repo=repo.repo,
            run_id=run.id,
            run_number=run.run_number,
            run_attempt=run.run_attempt,
            workflow_name=run.name[:300],
            workflow_path=run.workflow_path[:300],
            event=run.event[:50],
            head_branch=(run.head_branch or None) and run.head_branch[:300],
            head_sha=run.head_sha,
            conclusion=run.conclusion,
            html_url=run.html_url[:500],
            job_id=job.id,
            job_name=job.name,
            job_html_url=job.html_url[:500],
            failed_steps=[f"{s.number}. {s.name}"[:300] for s in job.failed_steps],
            log_source=imported.log_source,
            log_dropped_lines=imported.log_dropped_lines,
            files_fetched=[f.path for f in imported.files],
            files_missing=imported.missing_files,
        )
    )
    session.flush()
    return investigation


@dataclass(frozen=True)
class Withdrawal:
    investigation: Investigation
    withdrawn: list[int]
    skipped: list[int]  # already decided or withdrawn: left as they are
    closed: bool


def withdraw_proposals(
    session: Session,
    workspace_id: uuid.UUID,
    investigation_id: uuid.UUID,
    reasons: dict[int, str],
) -> Withdrawal | None:
    """Mark proposals as withdrawn (unsafe or non-actionable) without deleting anything: the
    proposal, its diff and its history stay, with the reason and time recorded and a timeline
    entry added. Only undecided proposals can be withdrawn. If none is left to decide, the
    investigation is closed without a decision. Returns None if the investigation is unknown."""
    investigation = session.execute(
        select(Investigation)
        .where(Investigation.id == investigation_id, Investigation.workspace_id == workspace_id)
        .with_for_update()
    ).scalar_one_or_none()
    if investigation is None:
        return None
    proposals = session.scalars(
        select(RemediationProposal)
        .where(RemediationProposal.investigation_id == investigation.id)
        .order_by(RemediationProposal.ordinal)
    ).all()
    withdrawn: list[int] = []
    skipped: list[int] = []
    for proposal in proposals:
        reason = reasons.get(proposal.ordinal)
        if reason is None:
            continue
        if proposal.status != "proposed":
            skipped.append(proposal.ordinal)
            continue
        proposal.status = "withdrawn"
        proposal.withdrawn_reason = reason[:1000]
        proposal.withdrawn_at = func.now()
        withdrawn.append(proposal.ordinal)
        append_event(
            session,
            workspace_id=workspace_id,
            investigation_id=investigation.id,
            attempt=0,
            node="audit",
            event_type="info",
            summary=f"Proposal {proposal.ordinal} withdrawn: {reason}",
        )
    session.flush()
    remaining = [p for p in proposals if p.status == "proposed"]
    closed = False
    if not remaining and investigation.status == "awaiting_approval":
        investigation.status = "completed"
        investigation.finished_at = func.now()
        closed = True
        append_event(
            session,
            workspace_id=workspace_id,
            investigation_id=investigation.id,
            attempt=0,
            node="audit",
            event_type="info",
            summary="No actionable proposal remains; the investigation is closed without a "
            "decision.",
        )
    return Withdrawal(investigation, withdrawn, skipped, closed)
