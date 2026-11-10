"""CI history endpoints (v1.1, D-052): track public repositories, sync their workflow history,
check data quality, and forget a repository or apply retention.

Tracking reads one repository description from https://api.github.com (read-only, public only).
A sync is a background job the operator starts; nothing syncs on its own. Every query filters by
the request's workspace, and a repository in another workspace answers 404.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from kensa.agents.pipeline import append_event
from kensa.api.deps import SessionDep, SettingsDep, WorkspaceDep
from kensa.api.github import github_client, http_error
from kensa.api.schemas import (
    ChangeFactorOut,
    ChangesOut,
    ChangeSuspectOut,
    DqFindingOut,
    EtlBatchOut,
    FingerprintOut,
    ForgetIn,
    InvestigationHistoryOut,
    PurgeOut,
    ResolutionIn,
    ResolutionOut,
    RetentionIn,
    SimilarFailureOut,
    SyncOut,
    TrackedRepositoryOut,
    TrackRepositoryIn,
)
from kensa.changes.store import load_analysis
from kensa.db.models import DqFinding, EtlBatch, Investigation, InvestigationFingerprint
from kensa.github.client import GitHubError
from kensa.github.urls import GitHubUrlError, parse_github_url
from kensa.history.fingerprints import (
    confirm_resolution,
    current_resolution,
    fingerprints_of,
    similar_failures,
)
from kensa.history.github import HistoryReader, RequestBudget
from kensa.history.purge import apply_retention, forget_repository
from kensa.history.quality import run_checks
from kensa.history.service import (
    TrackedSummary,
    enqueue_sync,
    get_tracked,
    summarize,
    track_repository,
)

router = APIRouter(tags=["history"])


def _out(summary: TrackedSummary) -> TrackedRepositoryOut:
    tracked = summary.repository
    return TrackedRepositoryOut(
        id=tracked.id,
        owner=tracked.owner,
        repo=tracked.repo,
        html_url=f"https://github.com/{tracked.owner}/{tracked.repo}",
        default_branch=tracked.default_branch,
        history_days=tracked.history_days,
        added_at=tracked.added_at,
        last_sync_at=tracked.last_sync_at,
        complete_through=(tracked.sync_state or {}).get("complete_through"),
        runs=summary.runs,
        failed_runs=summary.failed_runs,
        syncing=summary.syncing,
        last_batch=EtlBatchOut.model_validate(summary.last_batch) if summary.last_batch else None,
    )


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Repository not tracked.")


@router.get("/history/repositories")
def list_repositories(session: SessionDep, workspace: WorkspaceDep) -> list[TrackedRepositoryOut]:
    return [_out(s) for s in summarize(session, workspace.id)]


@router.post("/history/repositories", status_code=status.HTTP_201_CREATED)
def track(
    body: TrackRepositoryIn, session: SessionDep, workspace: WorkspaceDep, settings: SettingsDep
) -> TrackedRepositoryOut:
    try:
        ref = parse_github_url(body.url)
    except GitHubUrlError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if ref.run_id is not None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Give the repository's address, not a run's."
        )
    try:  # network first, outside any database transaction
        with github_client(settings) as client:
            meta = HistoryReader(client, RequestBudget(1)).repository(ref.owner, ref.repo)
        with session.begin():
            tracked, _ = track_repository(
                session, workspace.id, meta, body.history_days or settings.history_default_days
            )
            tracked_id = tracked.id
    except GitHubError as exc:
        raise http_error(exc) from exc
    summary = next(s for s in summarize(session, workspace.id) if s.repository.id == tracked_id)
    return _out(summary)


@router.post("/history/repositories/{tracked_id}/sync", status_code=status.HTTP_202_ACCEPTED)
def sync(tracked_id: uuid.UUID, session: SessionDep, workspace: WorkspaceDep) -> SyncOut:
    with session.begin():
        if get_tracked(session, workspace.id, tracked_id) is None:
            raise _not_found()
        result = enqueue_sync(session, workspace.id, tracked_id)
    return SyncOut(job_id=result.job_id, created=result.created)


@router.get("/history/repositories/{tracked_id}/batches")
def list_batches(
    tracked_id: uuid.UUID,
    session: SessionDep,
    workspace: WorkspaceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[EtlBatchOut]:
    if get_tracked(session, workspace.id, tracked_id) is None:
        raise _not_found()
    rows = session.execute(
        select(EtlBatch)
        .where(EtlBatch.workspace_id == workspace.id, EtlBatch.tracked_repository_id == tracked_id)
        .order_by(EtlBatch.started_at.desc())
        .limit(limit)
    ).scalars()
    return [EtlBatchOut.model_validate(b) for b in rows]


@router.post("/history/repositories/{tracked_id}/forget")
def forget(
    tracked_id: uuid.UUID, body: ForgetIn, session: SessionDep, workspace: WorkspaceDep
) -> PurgeOut:
    with session.begin():
        tracked = get_tracked(session, workspace.id, tracked_id)
        if tracked is None:
            raise _not_found()
        name = f"{tracked.owner}/{tracked.repo}"
        if body.confirm.strip().lower() != name.lower():
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Type the repository's full name to confirm.",
            )
        counts = forget_repository(session, workspace.id, tracked.owner, tracked.repo)
    return PurgeOut(counts=dict(counts))


@router.post("/history/retention")
def retention(body: RetentionIn, session: SessionDep, workspace: WorkspaceDep) -> PurgeOut:
    with session.begin():
        counts = apply_retention(session, workspace.id, body.older_than_days)
    return PurgeOut(counts=dict(counts))


@router.get("/history/quality")
def list_findings(
    session: SessionDep,
    workspace: WorkspaceDep,
    include_resolved: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[DqFindingOut]:
    query = select(DqFinding).where(DqFinding.workspace_id == workspace.id)
    if not include_resolved:
        query = query.where(DqFinding.resolved_at.is_(None))
    rows = session.execute(
        query.order_by(DqFinding.last_seen.desc(), DqFinding.check).limit(limit)
    ).scalars()
    return [DqFindingOut.model_validate(f) for f in rows]


@router.post("/history/quality/check")
def check_quality(session: SessionDep, workspace: WorkspaceDep) -> dict[str, int]:
    with session.begin():
        return dict(run_checks(session, workspace.id))


# --------------------------------------------- similar failures and resolutions (D-053) ---


def _investigation(
    session: SessionDep, workspace: WorkspaceDep, investigation_id: uuid.UUID
) -> Investigation:
    found = session.execute(
        select(Investigation).where(
            Investigation.id == investigation_id, Investigation.workspace_id == workspace.id
        )
    ).scalar_one_or_none()
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Investigation not found.")
    return found


@router.get("/investigations/{investigation_id}/history")
def investigation_history(
    investigation_id: uuid.UUID,
    session: SessionDep,
    workspace: WorkspaceDep,
    settings: SettingsDep,
) -> InvestigationHistoryOut:
    """Similar failures, shown as history: never evidence, never a reason to change a status.

    History matching is experimental and off by default (D-057): then only this
    investigation's own fingerprints are returned, with no matches and no counts."""
    _investigation(session, workspace, investigation_id)
    matching = settings.history_matching
    prints = fingerprints_of(session, investigation_id)
    counts = dict(
        session.execute(
            select(InvestigationFingerprint.fingerprint_id, func.count())
            .where(InvestigationFingerprint.fingerprint_id.in_([fp.id for fp, _ in prints]))
            .group_by(InvestigationFingerprint.fingerprint_id)
        ).all()
    )
    resolution = current_resolution(session, investigation_id)
    return InvestigationHistoryOut(
        matching=matching,
        fingerprints=[
            FingerprintOut(
                hash=fp.hash,
                role=role,
                category=fp.category,
                rule_id=fp.rule_id,
                subject=fp.subject,
                template=fp.template,
                kind=fp.kind,
                occurrences=int(counts.get(fp.id, 0)) if matching else None,
            )
            for fp, role in prints
        ],
        similar=[
            SimilarFailureOut.model_validate(item, from_attributes=True)
            for item in (
                similar_failures(session, workspace.id, investigation_id) if matching else []
            )
        ],
        resolution=ResolutionOut.model_validate(resolution) if resolution else None,
    )


@router.post("/investigations/{investigation_id}/resolution", status_code=status.HTTP_201_CREATED)
def confirm(
    investigation_id: uuid.UUID, body: ResolutionIn, session: SessionDep, workspace: WorkspaceDep
) -> ResolutionOut:
    """The operator's confirmed resolution (D-051 ``human_confirmed``). It is shown with later
    similar failures, and recorded on the timeline; the diagnosis and its status stay as they
    are."""
    with session.begin():
        _investigation(session, workspace, investigation_id)
        resolution = confirm_resolution(session, workspace.id, investigation_id, body.summary)
        append_event(
            session,
            workspace_id=workspace.id,
            investigation_id=investigation_id,
            attempt=0,
            node="resolution",
            event_type="info",
            summary="The operator confirmed how this failure was resolved.",
        )
        return ResolutionOut.model_validate(resolution)


@router.get("/investigations/{investigation_id}/changes")
def investigation_changes(
    investigation_id: uuid.UUID, session: SessionDep, workspace: WorkspaceDep
) -> ChangesOut | None:
    """How the run compares with the last comparable success, and the changes in between
    ranked by correlation (never as the cause). ``null`` when there is no analysis."""
    _investigation(session, workspace, investigation_id)
    loaded = load_analysis(session, investigation_id)
    if loaded is None:
        return None
    record, suspects = loaded
    return ChangesOut(
        comparability=record.comparability,
        reasons=list(record.reasons),
        factors=[ChangeFactorOut(**f) for f in record.factors],
        unverified=list(record.unverified),
        baseline_run_id=record.baseline_run_id,
        baseline_sha=record.baseline_sha,
        failed_sha=record.failed_sha,
        compare_status=record.compare_status,
        commits=record.commits,
        files=record.files,
        truncated=record.truncated,
        suspects=[ChangeSuspectOut.model_validate(s) for s in suspects],
    )
