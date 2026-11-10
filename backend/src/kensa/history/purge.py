"""Forget repository and retention (v1.1, D-052; the owner's privacy correction of 2026-11-09).

Both delete **whole** investigations: the log and its chunks and embeddings, error signatures,
evidence, the diagnosis and its citation quotes, timeline events, remediation proposals and
diffs, the decision, the imported-run record, jobs, and the LangGraph checkpoints (which hold
copies of the evidence). Nothing that could rebuild a log is left behind: a citation in another
investigation that quoted a deleted document is scrubbed too. Only non-reconstructable counts
remain (``purge_audits`` names its scope by a SHA-256 digest).

``PURGE_COVERAGE`` lists how every workspace-scoped table is handled; a test fails when a new
table is added without being listed here.
"""

import hashlib
import uuid
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.orm import Session

from kensa.db.models import (
    AnalyticsDaily,
    Chunk,
    CiRun,
    Citation,
    Diagnosis,
    Document,
    DqFinding,
    Investigation,
    Job,
    PurgeAudit,
    Repository,
    TrackedRepository,
    WorkflowRun,
)
from kensa.history.fingerprints import delete_orphans

REMOVED_QUOTE = "[removed: its source was deleted]"
# LangGraph's checkpoints hold copies of the state, evidence included. Literal statements:
# no table name is ever built from data.
CHECKPOINT_DELETES = {
    "checkpoint_writes": text(
        "DELETE FROM langgraph.checkpoint_writes WHERE thread_id = ANY(:threads)"
    ),
    "checkpoint_blobs": text(
        "DELETE FROM langgraph.checkpoint_blobs WHERE thread_id = ANY(:threads)"
    ),
    "checkpoints": text("DELETE FROM langgraph.checkpoints WHERE thread_id = ANY(:threads)"),
}

PURGE_COVERAGE: dict[str, str] = {
    "investigations": "deleted (the repository's, or older than the retention period)",
    "documents": "cascade from investigations; incident documents and snapshots deleted",
    "chunks": "cascade from documents (text and embeddings)",
    "error_signatures": "cascade from documents",
    "evidence": "cascade from investigations and from deleted chunks",
    "diagnoses": "cascade from investigations",
    "citations": "cascade from diagnoses; other quotes of deleted chunks are scrubbed",
    "agent_events": "cascade from investigations",
    "remediation_proposals": "cascade from investigations",
    "approval_decisions": "cascade from investigations",
    "workflow_runs": "cascade from investigations",
    "jobs": "cascade from investigations; the repository's sync jobs deleted",
    "repositories": "the repository's GitHub snapshots deleted (retention: unused ones)",
    "tracked_repositories": "deleted (Forget repository)",
    "etl_batches": "cascade from tracked_repositories",
    "ci_runs": "cascade from tracked_repositories; retention deletes old ones",
    "ci_jobs": "cascade from ci_runs",
    "dq_findings": "cascade from tracked_repositories or investigations; old resolved ones",
    "purge_audits": "kept: a digest of the scope and counts only",
    "failure_fingerprints": "deleted once no investigation references them (orphans)",
    "investigation_fingerprints": "cascade from investigations",
    "resolutions": "cascade from investigations",
    "change_analyses": "cascade from investigations",
    "change_suspects": "cascade from change_analyses",
    "analytics_daily": "the repository's rows deleted; otherwise counts only (kept)",
    "analytics_watermarks": "kept: one refresh time per workspace",
}


def digest(scope: str) -> str:
    return hashlib.sha256(scope.encode("utf-8")).hexdigest()


def _documents_of(session: Session, workspace_id: uuid.UUID, where: object) -> list[uuid.UUID]:
    return list(
        session.execute(
            select(Document.id).where(Document.workspace_id == workspace_id, where)  # type: ignore[arg-type]
        ).scalars()
    )


def _scrub_quotes(
    session: Session, document_ids: Sequence[uuid.UUID], keep_out: Sequence[uuid.UUID]
) -> int:
    """Replace quotes that other investigations took from documents about to be deleted."""
    if not document_ids:
        return 0
    chunk_ids = select(Chunk.id).where(Chunk.document_id.in_(document_ids))
    deleted_diagnoses = select(Diagnosis.id).where(Diagnosis.investigation_id.in_(keep_out))
    result = session.execute(
        update(Citation)
        .where(Citation.chunk_id.in_(chunk_ids), Citation.diagnosis_id.not_in(deleted_diagnoses))
        .values(quote=REMOVED_QUOTE)
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def _delete_documents(
    session: Session,
    document_ids: Sequence[uuid.UUID],
    keep_out: Sequence[uuid.UUID],
    counts: Counter[str],
) -> int:
    if not document_ids:
        return 0
    counts["quotes_scrubbed"] += _scrub_quotes(session, document_ids, keep_out)
    result = session.execute(delete(Document).where(Document.id.in_(document_ids)))
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def purge_investigations(
    session: Session, workspace_id: uuid.UUID, investigation_ids: Sequence[uuid.UUID]
) -> Counter[str]:
    """Delete these investigations and everything derived from them (see the module doc)."""
    counts: Counter[str] = Counter()
    ids = list(
        session.execute(
            select(Investigation.id).where(
                Investigation.workspace_id == workspace_id, Investigation.id.in_(investigation_ids)
            )
        ).scalars()
    )
    if not ids:
        return counts
    threads = [f"investigation-{i}" for i in ids]
    for table, statement in CHECKPOINT_DELETES.items():
        result = session.execute(statement, {"threads": threads})
        counts[f"langgraph_{table}"] += int(result.rowcount or 0)  # type: ignore[attr-defined]
    incident_docs = _documents_of(
        session,
        workspace_id,
        (Document.source_type == "incident") & Document.name.in_([f"incident/{i}" for i in ids]),
    )
    counts["incident_documents"] += _delete_documents(session, incident_docs, ids, counts)
    own_docs = _documents_of(session, workspace_id, Document.investigation_id.in_(ids))
    counts["quotes_scrubbed"] += _scrub_quotes(session, own_docs, ids)
    result = session.execute(
        delete(Job).where(
            Job.workspace_id == workspace_id,
            or_(
                Job.investigation_id.in_(ids),
                Job.payload["investigation_id"].astext.in_([str(i) for i in ids]),
            ),
        )
    )
    counts["jobs"] += int(result.rowcount or 0)  # type: ignore[attr-defined]
    result = session.execute(delete(Investigation).where(Investigation.id.in_(ids)))
    counts["investigations"] += int(result.rowcount or 0)  # type: ignore[attr-defined]
    counts["fingerprints"] += delete_orphans(session, workspace_id)
    return counts


def repository_investigations(
    session: Session, workspace_id: uuid.UUID, owner: str, repo: str
) -> list[uuid.UUID]:
    return list(
        session.execute(
            select(WorkflowRun.investigation_id).where(
                WorkflowRun.workspace_id == workspace_id,
                func.lower(WorkflowRun.owner) == owner.lower(),
                func.lower(WorkflowRun.repo) == repo.lower(),
            )
        ).scalars()
    )


def forget_repository(
    session: Session, workspace_id: uuid.UUID, owner: str, repo: str
) -> Counter[str]:
    """Delete every trace of one GitHub repository from this workspace."""
    ids = repository_investigations(session, workspace_id, owner, repo)
    counts = purge_investigations(session, workspace_id, ids)
    snapshots = list(
        session.execute(
            select(Repository.id).where(
                Repository.workspace_id == workspace_id,
                Repository.provider == "github",
                func.lower(Repository.name) == f"{owner}/{repo}".lower(),
            )
        ).scalars()
    )
    snapshot_docs = _documents_of(session, workspace_id, Document.repository_id.in_(snapshots))
    counts["snapshot_documents"] += _delete_documents(session, snapshot_docs, ids, counts)
    if snapshots:
        result = session.execute(delete(Repository).where(Repository.id.in_(snapshots)))
        counts["snapshots"] += int(result.rowcount or 0)  # type: ignore[attr-defined]
    tracked = list(
        session.execute(
            select(TrackedRepository.id).where(
                TrackedRepository.workspace_id == workspace_id,
                func.lower(TrackedRepository.owner) == owner.lower(),
                func.lower(TrackedRepository.repo) == repo.lower(),
            )
        ).scalars()
    )
    if tracked:
        result = session.execute(
            delete(Job).where(
                Job.workspace_id == workspace_id,
                Job.payload["tracked_repository_id"].astext.in_([str(t) for t in tracked]),
            )
        )
        counts["jobs"] += int(result.rowcount or 0)  # type: ignore[attr-defined]
        runs = session.execute(
            select(func.count()).select_from(CiRun).where(CiRun.tracked_repository_id.in_(tracked))
        ).scalar_one()
        counts["ci_runs"] += int(runs)
        result = session.execute(delete(TrackedRepository).where(TrackedRepository.id.in_(tracked)))
        counts["tracked_repositories"] += int(result.rowcount or 0)  # type: ignore[attr-defined]
    result = session.execute(
        delete(AnalyticsDaily).where(
            AnalyticsDaily.workspace_id == workspace_id,
            func.lower(AnalyticsDaily.repository) == f"{owner}/{repo}".lower(),
        )
    )
    counts["analytics_rows"] += int(result.rowcount or 0)  # type: ignore[attr-defined]
    session.add(
        PurgeAudit(
            workspace_id=workspace_id,
            action="forget_repository",
            scope_digest=digest(f"{owner}/{repo}".lower()),
            counts=dict(counts),
        )
    )
    return counts


def apply_retention(
    session: Session, workspace_id: uuid.UUID, older_than_days: int, now: datetime | None = None
) -> Counter[str]:
    """Delete investigations and run history older than ``older_than_days``, completely."""
    if older_than_days < 1:
        raise ValueError("retention must keep at least one day")
    cutoff = (now or datetime.now(UTC)) - timedelta(days=older_than_days)
    ids = list(
        session.execute(
            select(Investigation.id).where(
                Investigation.workspace_id == workspace_id, Investigation.created_at < cutoff
            )
        ).scalars()
    )
    counts = purge_investigations(session, workspace_id, ids)
    used = select(Investigation.repository_id).where(Investigation.repository_id.is_not(None))
    unused = list(
        session.execute(
            select(Repository.id).where(
                Repository.workspace_id == workspace_id,
                Repository.provider == "github",
                Repository.created_at < cutoff,
                Repository.id.not_in(used),
            )
        ).scalars()
    )
    snapshot_docs = _documents_of(session, workspace_id, Document.repository_id.in_(unused))
    counts["snapshot_documents"] += _delete_documents(session, snapshot_docs, ids, counts)
    if unused:
        result = session.execute(delete(Repository).where(Repository.id.in_(unused)))
        counts["snapshots"] += int(result.rowcount or 0)  # type: ignore[attr-defined]
    result = session.execute(
        delete(CiRun).where(CiRun.workspace_id == workspace_id, CiRun.gh_created_at < cutoff)
    )
    counts["ci_runs"] += int(result.rowcount or 0)  # type: ignore[attr-defined]
    result = session.execute(
        delete(DqFinding).where(
            DqFinding.workspace_id == workspace_id,
            DqFinding.resolved_at.is_not(None),
            DqFinding.resolved_at < cutoff,
        )
    )
    counts["dq_findings"] += int(result.rowcount or 0)  # type: ignore[attr-defined]
    session.add(
        PurgeAudit(
            workspace_id=workspace_id,
            action="retention",
            scope_digest=digest(f"retention:{cutoff.isoformat()}"),
            counts=dict(counts),
        )
    )
    return counts
