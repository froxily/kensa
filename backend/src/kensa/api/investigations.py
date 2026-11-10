"""Investigation endpoints. Every query filters by the request's workspace (D-011); an
investigation in another workspace is indistinguishable from one that does not exist (404)."""

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import Engine, case, func, select
from sqlalchemy.orm import Session

from kensa.agents.pipeline import append_event
from kensa.api.deps import EngineDep, SessionDep, SettingsDep, Workspace, WorkspaceDep
from kensa.api.github import github_client, http_error
from kensa.api.schemas import (
    AgentEventOut,
    CitationOut,
    CreateInvestigation,
    DecisionIn,
    DecisionOut,
    DecisionResult,
    DiagnosisOut,
    DocumentContent,
    DocumentMeta,
    EvidenceOut,
    InvestigationDetail,
    InvestigationPage,
    InvestigationSummary,
    ProposalOut,
    SampleOut,
    SignatureOut,
    WorkflowRunOut,
)
from kensa.changes.service import analyze_import
from kensa.changes.store import save_analysis
from kensa.core.config import Settings
from kensa.db.models import (
    AgentEvent,
    ApprovalDecision,
    Chunk,
    Citation,
    Diagnosis,
    Document,
    ErrorSignature,
    Evidence,
    Investigation,
    RemediationProposal,
    Repository,
    WorkflowRun,
)
from kensa.github.client import GitHubError
from kensa.github.importer import GitHubImport, import_run
from kensa.github.urls import GitHubRef
from kensa.ingestion.normalize import LogRejectedError, strip_timestamp
from kensa.investigations.samples import SAMPLES, get_sample
from kensa.investigations.service import (
    DecisionConflictError,
    InvestigationStateError,
    NewInvestigation,
    create_github_investigation,
    create_investigation,
    decide,
    retry_investigation,
)

router = APIRouter(tags=["investigations"])
# Settled states: the live stream ends; nothing runs until the user acts again.
TERMINAL = {"awaiting_approval", "completed", "failed"}
MAX_SIGNATURES_SHOWN = 50


def _summary(investigation: Investigation, diagnosis: Diagnosis | None) -> InvestigationSummary:
    summary = InvestigationSummary.model_validate(investigation)
    if diagnosis is not None:
        summary.category = diagnosis.category
        summary.verification_status = diagnosis.verification_status
    return summary


def _load(session: Session, workspace: Workspace, investigation_id: uuid.UUID) -> Investigation:
    investigation = session.scalars(
        select(Investigation).where(
            Investigation.id == investigation_id, Investigation.workspace_id == workspace.id
        )
    ).one_or_none()
    if investigation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Investigation not found.")
    return investigation


@router.get("/samples")
def list_samples() -> list[SampleOut]:
    return [SampleOut(id=s.id, title=s.title, description=s.description) for s in SAMPLES]


def _import_summary(imported: GitHubImport) -> str:
    run, job = imported.run, imported.job
    steps = ", ".join(s.name for s in job.failed_steps) or "none reported"
    log = "downloaded from GitHub" if imported.log_source == "github" else "pasted"
    missing = f"; {len(imported.missing_files)} unavailable" if imported.missing_files else ""
    return (
        f"Imported {imported.repo.owner}/{imported.repo.repo} run #{run.run_number} "
        f'(attempt {run.run_attempt}), job "{job.name}" (failed step: {steps}) at commit '
        f"{run.head_sha[:7]}: log {log}, {len(imported.files)} repository file(s){missing}."
    )


def _earlier_import(
    session: Session, workspace: Workspace, imported: GitHubImport, provider: str
) -> Investigation | None:
    """v1.1: the same job attempt (at the same commit), already investigated with the same
    provider."""
    return session.scalars(
        select(Investigation)
        .join(WorkflowRun, WorkflowRun.investigation_id == Investigation.id)
        .where(
            WorkflowRun.workspace_id == workspace.id,
            WorkflowRun.owner == imported.repo.owner,
            WorkflowRun.repo == imported.repo.repo,
            WorkflowRun.run_id == imported.run.id,
            WorkflowRun.run_attempt == imported.run.run_attempt,
            WorkflowRun.job_id == imported.job.id,
            WorkflowRun.head_sha == imported.run.head_sha,
            Investigation.provider == provider,
        )
        .order_by(Investigation.created_at)
        .limit(1)
    ).one_or_none()


def _create_from_github(
    body: CreateInvestigation,
    session: SessionDep,
    workspace: Workspace,
    settings: Settings,
    response: Response,
) -> InvestigationSummary:
    target = body.github
    if target is None:  # guaranteed by CreateInvestigation's validator
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "github is required")
    ref = GitHubRef(target.owner, target.repo, target.run_id, target.attempt, target.job_id)
    try:  # network first, outside any database transaction
        with github_client(settings) as client:
            imported = import_run(
                client,
                ref,
                job_id=target.job_id,
                pasted_log=body.log_text,
                max_files=settings.github_max_files,
            )
    except GitHubError as exc:
        raise http_error(exc) from exc
    provider = body.provider or settings.inference_provider
    with session.begin():
        earlier = _earlier_import(session, workspace, imported, provider)
        if earlier is not None:
            # Importing the same job again opens its investigation instead of a duplicate.
            diagnosis = session.scalars(
                select(Diagnosis).where(Diagnosis.investigation_id == earlier.id)
            ).one_or_none()
            response.status_code = status.HTTP_200_OK
            return _summary(earlier, diagnosis)
    changes = None
    if settings.change_analysis:  # v1.1 (D-054): network, before anything is stored
        with github_client(settings) as client:
            changes = analyze_import(client, imported, settings)
    try:
        with session.begin():
            investigation = create_github_investigation(
                session, workspace.id, imported, provider, settings.llm_model
            )
            if changes is not None:
                save_analysis(
                    session,
                    workspace.id,
                    investigation.id,
                    imported.run.head_sha,
                    changes,
                    diff_evidence=settings.change_diff_evidence,
                )
            append_event(
                session,
                workspace_id=workspace.id,
                investigation_id=investigation.id,
                attempt=0,
                node="github",
                event_type="completed",
                summary=_import_summary(imported),
            )
    except LogRejectedError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return _summary(investigation, None)


@router.post("/investigations", status_code=status.HTTP_201_CREATED)
def create(
    body: CreateInvestigation,
    session: SessionDep,
    workspace: WorkspaceDep,
    settings: SettingsDep,
    response: Response,
) -> InvestigationSummary:
    if body.source == "github":
        return _create_from_github(body, session, workspace, settings, response)
    title: str | None = body.title
    if body.sample_id is not None:
        sample = get_sample(body.sample_id)
        if sample is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Sample not found.")
        log_text, name, title = sample.read(), sample.filename, title or sample.title
    else:
        log_text, name = body.log_text or "", body.document_name
    provider = body.provider or settings.inference_provider
    new = NewInvestigation(title, body.source, provider, name, log_text)
    try:
        with session.begin():
            investigation = create_investigation(session, workspace.id, new, settings.llm_model)
    except LogRejectedError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return _summary(investigation, None)


@router.get("/investigations")
def list_investigations(
    session: SessionDep,
    workspace: WorkspaceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> InvestigationPage:
    scope = Investigation.workspace_id == workspace.id
    total = session.scalar(select(func.count()).select_from(Investigation).where(scope)) or 0
    rows = session.execute(
        select(Investigation, Diagnosis)
        .outerjoin(Diagnosis, Diagnosis.investigation_id == Investigation.id)
        .where(scope)
        .order_by(Investigation.created_at.desc(), Investigation.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return InvestigationPage(items=[_summary(i, d) for i, d in rows], total=total)


@router.get("/investigations/{investigation_id}")
def get_investigation(
    investigation_id: uuid.UUID, session: SessionDep, workspace: WorkspaceDep
) -> InvestigationDetail:
    investigation = _load(session, workspace, investigation_id)
    diagnosis = session.scalars(
        select(Diagnosis).where(Diagnosis.investigation_id == investigation.id)
    ).one_or_none()
    documents = session.scalars(
        select(Document)
        .where(Document.investigation_id == investigation.id)
        # The log first (the UI shows the first document as the log), then a stable order:
        # a GitHub import saves its log and diff documents in one transaction, so created_at
        # ties and alone would leave their order to the database.
        .order_by(
            case((Document.source_type == "log", 0), else_=1),
            Document.created_at,
            Document.name,
            Document.id,
        )
    ).all()
    evidence_rows = session.execute(
        select(
            Evidence,
            Chunk,
            Document.name,
            Document.source_type,
            Repository.provider,
            Repository.name,
            Repository.commit_sha,
        )
        .join(Chunk, Chunk.id == Evidence.chunk_id)
        .join(Document, Document.id == Chunk.document_id)
        .outerjoin(Repository, Repository.id == Document.repository_id)
        .where(Evidence.investigation_id == investigation.id)
        .order_by(Evidence.rank)
    ).all()
    github_run = session.scalars(
        select(WorkflowRun).where(WorkflowRun.investigation_id == investigation.id)
    ).one_or_none()
    signatures = session.scalars(
        select(ErrorSignature)
        .where(ErrorSignature.document_id.in_([d.id for d in documents]))
        .order_by(ErrorSignature.weight.desc(), ErrorSignature.line_number)
        .limit(MAX_SIGNATURES_SHOWN)
    ).all()

    diagnosis_out = None
    if diagnosis is not None:
        citations = session.scalars(
            select(Citation).where(Citation.diagnosis_id == diagnosis.id).order_by(Citation.ordinal)
        ).all()
        diagnosis_out = DiagnosisOut(
            category=diagnosis.category,
            rule_category=diagnosis.rule_category,
            summary=diagnosis.summary,
            root_cause=diagnosis.root_cause,
            confidence=diagnosis.confidence,
            uncertainty=diagnosis.uncertainty,
            recommended_fixes=list(diagnosis.recommended_fixes),
            verification_status=diagnosis.verification_status,
            verification_notes=list(diagnosis.verification_notes),
            provider=diagnosis.provider,
            model=diagnosis.model,
            prompt_tokens=diagnosis.prompt_tokens,
            output_tokens=diagnosis.output_tokens,
            duration_ms=diagnosis.duration_ms,
            evidence_complete=diagnosis.evidence_complete,
            diagnosis_attempts=diagnosis.diagnosis_attempts,
            citations=[
                CitationOut(
                    ordinal=c.ordinal,
                    evidence_label=c.evidence_label,
                    line_number=c.line_number,
                    quote=c.quote,
                    valid=c.valid,
                    rejection_reason=c.rejection_reason,
                )
                for c in citations
            ],
        )

    proposals = session.scalars(
        select(RemediationProposal)
        .where(RemediationProposal.investigation_id == investigation.id)
        .order_by(RemediationProposal.ordinal)
    ).all()
    decision = session.scalars(
        select(ApprovalDecision).where(ApprovalDecision.investigation_id == investigation.id)
    ).one_or_none()

    summary = _summary(investigation, diagnosis)
    return InvestigationDetail(
        **summary.model_dump(),
        documents=[DocumentMeta.model_validate(d) for d in documents],
        diagnosis=diagnosis_out,
        evidence=[
            EvidenceOut(
                label=e.label,
                rank=e.rank,
                score=e.score,
                channels=list(e.channels),
                document_id=chunk.document_id,
                document_name=name,
                source_type=source_type,
                commit_sha=commit_sha,
                source_url=_blob_url(repo_provider, repo_name, commit_sha, name, chunk),
                kind=chunk.kind,
                step_name=chunk.step_name,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                lines=[strip_timestamp(line) for line in chunk.content.split("\n")],
            )
            for e, chunk, name, source_type, repo_provider, repo_name, commit_sha in evidence_rows
        ],
        signatures=[
            SignatureOut(
                line_number=s.line_number,
                kind=s.kind,
                value=s.value,
                category_hint=s.category_hint,
                weight=s.weight,
                excerpt=s.excerpt,
            )
            for s in signatures
        ],
        proposals=[ProposalOut.model_validate(p) for p in proposals],
        decision=DecisionOut.model_validate(decision) if decision else None,
        github_run=WorkflowRunOut.model_validate(github_run) if github_run else None,
    )


def _blob_url(
    provider: str | None, repository: str | None, sha: str | None, path: str, chunk: Chunk
) -> str | None:
    """A link to the cited lines at the exact commit the run used."""
    if provider != "github" or not repository or not sha:
        return None
    return (
        f"https://github.com/{repository}/blob/{sha}/{quote(path, safe='/')}"
        f"#L{chunk.start_line}-L{chunk.end_line}"
    )


@router.get("/investigations/{investigation_id}/documents/{document_id}")
def get_document(
    investigation_id: uuid.UUID,
    document_id: uuid.UUID,
    session: SessionDep,
    workspace: WorkspaceDep,
) -> DocumentContent:
    investigation = _load(session, workspace, investigation_id)
    document = session.scalars(
        select(Document).where(
            Document.id == document_id,
            Document.investigation_id == investigation.id,
            Document.workspace_id == workspace.id,
        )
    ).one_or_none()
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    meta = DocumentMeta.model_validate(document)
    lines = [strip_timestamp(line) for line in document.content.split("\n")]
    return DocumentContent(**meta.model_dump(), lines=lines)


def _events_after(
    session: Session, workspace: Workspace, investigation_id: uuid.UUID, after: int
) -> list[AgentEventOut]:
    rows = session.scalars(
        select(AgentEvent)
        .where(
            AgentEvent.investigation_id == investigation_id,
            AgentEvent.workspace_id == workspace.id,
            AgentEvent.seq > after,
        )
        .order_by(AgentEvent.seq)
        .limit(500)
    ).all()
    return [AgentEventOut.model_validate(row) for row in rows]


@router.get("/investigations/{investigation_id}/events")
def list_events(
    investigation_id: uuid.UUID,
    session: SessionDep,
    workspace: WorkspaceDep,
    after: Annotated[int, Query(ge=0)] = 0,
) -> list[AgentEventOut]:
    _load(session, workspace, investigation_id)
    return _events_after(session, workspace, investigation_id, after)


@router.post("/investigations/{investigation_id}/retry")
def retry(
    investigation_id: uuid.UUID, session: SessionDep, workspace: WorkspaceDep
) -> InvestigationSummary:
    try:
        with session.begin():
            investigation = retry_investigation(session, workspace.id, investigation_id)
    except InvestigationStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    if investigation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Investigation not found.")
    return _summary(investigation, None)


@router.post("/investigations/{investigation_id}/decision")
def record_decision(
    investigation_id: uuid.UUID, body: DecisionIn, session: SessionDep, workspace: WorkspaceDep
) -> DecisionResult:
    """Approve or reject the remediation proposals. Approval records the decision only; Kensa
    never changes a repository. Repeating the recorded decision is a no-op (``created`` false);
    a different decision, or an investigation not awaiting approval, is a 409."""
    try:
        with session.begin():
            record = decide(session, workspace.id, investigation_id, body.decision, body.note)
            if record is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Investigation not found.")
            result = DecisionResult(
                decision=DecisionOut.model_validate(record.decision),
                created=record.created,
                status=record.investigation.status,
            )
    except DecisionConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except InvestigationStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return result


def _poll(
    engine: Engine, workspace: Workspace, investigation_id: uuid.UUID, after: int
) -> tuple[list[AgentEventOut], str | None]:
    with Session(engine) as session:
        status_value = session.scalar(
            select(Investigation.status).where(
                Investigation.id == investigation_id, Investigation.workspace_id == workspace.id
            )
        )
        return _events_after(session, workspace, investigation_id, after), status_value


def _sse(event: str, data: str, event_id: int | None = None) -> str:
    prefix = f"id: {event_id}\n" if event_id is not None else ""
    return f"{prefix}event: {event}\ndata: {data}\n\n"


@router.get("/investigations/{investigation_id}/stream")
async def stream(
    investigation_id: uuid.UUID,
    request: Request,
    engine: EngineDep,
    workspace: WorkspaceDep,
    settings: SettingsDep,
    after: Annotated[int, Query(ge=0)] = 0,
    last_event_id: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    """Server-sent events: ``agent_event`` per timeline entry, ``status`` on change, ``end``
    once the investigation is finished and every event has been sent."""
    if last_event_id is not None and last_event_id.isdigit():
        after = max(after, int(last_event_id))  # browser reconnect resumes where it left off
    _, initial = await run_in_threadpool(_poll, engine, workspace, investigation_id, after)
    if initial is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Investigation not found.")

    async def events() -> AsyncIterator[str]:
        last_seq, last_status = after, None
        deadline = time.monotonic() + settings.stream_max_seconds
        last_sent = time.monotonic()
        yield "retry: 2000\n\n"
        while time.monotonic() < deadline and not await request.is_disconnected():
            batch, current = await run_in_threadpool(
                _poll, engine, workspace, investigation_id, last_seq
            )
            for event in batch:
                last_seq = event.seq
                yield _sse("agent_event", event.model_dump_json(), event.seq)
            if current != last_status:
                last_status = current
                yield _sse("status", json.dumps({"status": current}))
            if batch or current != last_status:
                last_sent = time.monotonic()
            if current in TERMINAL and not batch:
                yield _sse("end", "{}")
                return
            if time.monotonic() - last_sent > 15:
                yield ": keep-alive\n\n"
                last_sent = time.monotonic()
            await asyncio.sleep(0.5)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
