"""Storing fingerprints and finding similar failures (v1.1, D-053).

Similar failures are shown next to an investigation as **history, never as evidence**: they do
not enter the diagnosis prompt, cannot be cited, and cannot change a status (D-051). Each match
says how it matched and what is known about it:

* **Match strength:** a shared **exact** primary fingerprint is a recurrence ("same
  failure"); a shared exact secondary fingerprint is "related"; everything else, including a
  shared *approximate* fingerprint, is "similar text" and is never presented as a recurrence
  (D-057). Only fingerprints of the current ``FINGERPRINT_VERSION`` take part.
* **What the earlier conclusion rests on:** a model hypothesis, a verifier-corroborated cause,
  or a resolution the operator confirmed.

Matches never include the investigation itself, another import of the same job attempt, or an
investigation of an identical log, so one failure cannot count as its own recurrence.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, exists, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from kensa.analysis.causes import assess_causes
from kensa.analysis.classifier import classify
from kensa.analysis.fingerprint import FINGERPRINT_VERSION, Fingerprint, fingerprints
from kensa.analysis.signatures import extract_signatures
from kensa.db.models import (
    Diagnosis,
    Document,
    FailureFingerprint,
    Investigation,
    InvestigationFingerprint,
    Resolution,
    WorkflowRun,
)

SAME_FAILURE, RELATED, SIMILAR_TEXT = 1.0, 0.6, 0.5
TEXT_CANDIDATES = 20
_TERM = re.compile(r"[a-z0-9_]{3,}")


@dataclass(frozen=True)
class SimilarFailure:
    investigation_id: uuid.UUID
    title: str
    created_at: datetime
    match: str  # "same_failure" | "related" | "similar_text"
    score: float
    earlier: bool
    category: str  # the fingerprint's (rule-derived) category
    diagnosis_category: str | None
    verification_status: str | None
    provenance: str  # "human_confirmed" | "verifier_corroborated" | "model_hypothesis" | "none"
    resolution: str | None


def record_fingerprints(
    session: Session,
    workspace_id: uuid.UUID,
    investigation_id: uuid.UUID,
    prints: list[Fingerprint],
) -> list[uuid.UUID]:
    """Upsert the fingerprints and link them to the investigation (idempotent)."""
    ids: list[uuid.UUID] = []
    for fp in prints:
        upsert = pg_insert(FailureFingerprint).values(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            version=FINGERPRINT_VERSION,
            hash=fp.hash,
            category=fp.category,
            rule_id=fp.rule_id[:100],
            subject=fp.subject,
            template=fp.template,
            kind=fp.kind,
        )
        stmt = upsert.on_conflict_do_update(
            constraint="uq_failure_fingerprints_hash", set_={"hash": upsert.excluded.hash}
        ).returning(FailureFingerprint.id)
        fingerprint_id = session.execute(stmt).scalar_one()
        session.execute(
            pg_insert(InvestigationFingerprint)
            .values(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                investigation_id=investigation_id,
                fingerprint_id=fingerprint_id,
                role=fp.role,
            )
            .on_conflict_do_nothing(constraint="uq_investigation_fingerprints_link")
        )
        ids.append(fingerprint_id)
    return ids


def fingerprint_log(
    session: Session, workspace_id: uuid.UUID, investigation_id: uuid.UUID, log_text: str
) -> list[uuid.UUID]:
    """Fingerprint a stored (redacted) log, exactly as at creation; used by the backfill.
    Links to fingerprints of older versions are replaced."""
    older = select(FailureFingerprint.id).where(FailureFingerprint.version != FINGERPRINT_VERSION)
    session.execute(
        delete(InvestigationFingerprint).where(
            InvestigationFingerprint.investigation_id == investigation_id,
            InvestigationFingerprint.fingerprint_id.in_(older),
        )
    )
    lines = log_text.split("\n")
    signatures = extract_signatures(lines)
    causes = assess_causes(lines)
    rule = classify(signatures, causes)
    return record_fingerprints(
        session,
        workspace_id,
        investigation_id,
        fingerprints(lines, signatures, causes, rule.category),
    )


def backfill(
    session: Session, workspace_id: uuid.UUID, limit: int = 500, after: uuid.UUID | None = None
) -> list[uuid.UUID]:
    """Fingerprint investigations that have no fingerprint of the current version yet, in id
    order after ``after``. Returns the ids it processed: a log without any signal yields no
    fingerprint, so callers page with ``after`` instead of re-reading the same investigations."""
    linked = (
        select(InvestigationFingerprint.investigation_id)
        .join(FailureFingerprint, FailureFingerprint.id == InvestigationFingerprint.fingerprint_id)
        .where(FailureFingerprint.version == FINGERPRINT_VERSION)
    )
    query = (
        select(Investigation.id, Document.content)
        .join(Document, Document.investigation_id == Investigation.id)
        .where(
            Investigation.workspace_id == workspace_id,
            Document.source_type == "log",
            Investigation.id.not_in(linked),
        )
        .order_by(Investigation.id)
        .limit(limit)
    )
    if after is not None:
        query = query.where(Investigation.id > after)
    rows = session.execute(query).all()
    for investigation_id, content in rows:
        fingerprint_log(session, workspace_id, investigation_id, content)
    return [row[0] for row in rows]


def delete_orphans(session: Session, workspace_id: uuid.UUID) -> int:
    """Fingerprints no investigation references any more (after a purge) hold a template of a
    deleted log line: they go too."""
    result = session.execute(
        delete(FailureFingerprint).where(
            FailureFingerprint.workspace_id == workspace_id,
            ~exists().where(InvestigationFingerprint.fingerprint_id == FailureFingerprint.id),
        )
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def confirm_resolution(
    session: Session, workspace_id: uuid.UUID, investigation_id: uuid.UUID, summary: str
) -> Resolution:
    """The operator's confirmed resolution; it supersedes their earlier one."""
    now = datetime.now(UTC)
    session.execute(
        update(Resolution)
        .where(
            Resolution.workspace_id == workspace_id,
            Resolution.investigation_id == investigation_id,
            Resolution.superseded_at.is_(None),
        )
        .values(superseded_at=now)
    )
    resolution = Resolution(
        workspace_id=workspace_id,
        investigation_id=investigation_id,
        provenance="human_confirmed",
        summary=summary.strip()[:1000],
    )
    session.add(resolution)
    session.flush()
    return resolution


def current_resolution(session: Session, investigation_id: uuid.UUID) -> Resolution | None:
    return session.execute(
        select(Resolution)
        .where(Resolution.investigation_id == investigation_id, Resolution.superseded_at.is_(None))
        .order_by(Resolution.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def fingerprints_of(
    session: Session, investigation_id: uuid.UUID
) -> list[tuple[FailureFingerprint, str]]:
    rows = session.execute(
        select(FailureFingerprint, InvestigationFingerprint.role)
        .join(
            InvestigationFingerprint,
            InvestigationFingerprint.fingerprint_id == FailureFingerprint.id,
        )
        .where(
            InvestigationFingerprint.investigation_id == investigation_id,
            FailureFingerprint.version == FINGERPRINT_VERSION,
        )
        .order_by(InvestigationFingerprint.role, FailureFingerprint.hash)
    ).all()
    return [(row[0], row[1]) for row in rows]


def _excluded(
    session: Session, workspace_id: uuid.UUID, investigation_id: uuid.UUID
) -> set[uuid.UUID]:
    """The investigation, other imports of its job attempt, and investigations of an identical
    log: none of them is evidence that the failure happened again."""
    excluded = {investigation_id}
    run = session.execute(
        select(WorkflowRun).where(WorkflowRun.investigation_id == investigation_id)
    ).scalar_one_or_none()
    if run is not None:
        excluded |= set(
            session.execute(
                select(WorkflowRun.investigation_id).where(
                    WorkflowRun.workspace_id == workspace_id,
                    WorkflowRun.owner == run.owner,
                    WorkflowRun.repo == run.repo,
                    WorkflowRun.run_id == run.run_id,
                    WorkflowRun.run_attempt == run.run_attempt,
                    WorkflowRun.job_id == run.job_id,
                )
            ).scalars()
        )
    log_hash = select(Document.content_hash).where(
        Document.investigation_id == investigation_id, Document.source_type == "log"
    )
    excluded |= set(
        session.execute(
            select(Investigation.id)
            .join(Document, Document.investigation_id == Investigation.id)
            .where(
                Document.workspace_id == workspace_id,
                Document.source_type == "log",
                Document.content_hash.in_(log_hash),
            )
        ).scalars()
    )
    return excluded


def _or_query(text_value: str) -> str:
    terms = [t for t in dict.fromkeys(_TERM.findall(text_value.lower())) if t not in {"n", "ts"}]
    return " | ".join(terms[:30])


def similar_failures(
    session: Session,
    workspace_id: uuid.UUID,
    investigation_id: uuid.UUID,
    *,
    limit: int = 5,
    earlier_only: bool = False,
) -> list[SimilarFailure]:
    current = session.execute(
        select(Investigation.created_at).where(
            Investigation.id == investigation_id, Investigation.workspace_id == workspace_id
        )
    ).scalar_one_or_none()
    if current is None:
        return []
    own = fingerprints_of(session, investigation_id)
    if not own:
        return []
    excluded = _excluded(session, workspace_id, investigation_id)
    best: dict[uuid.UUID, tuple[float, str, str]] = {}  # investigation -> score, match, category

    def offer(candidate: uuid.UUID, score: float, match: str, category: str) -> None:
        if candidate in excluded:
            return
        if candidate not in best or best[candidate][0] < score:
            best[candidate] = (score, match, category)

    own_ids = {fp.id: role for fp, role in own}
    links = session.execute(
        select(
            InvestigationFingerprint.investigation_id,
            InvestigationFingerprint.fingerprint_id,
            InvestigationFingerprint.role,
            FailureFingerprint.category,
            FailureFingerprint.kind,
        )
        .join(FailureFingerprint, FailureFingerprint.id == InvestigationFingerprint.fingerprint_id)
        .where(
            InvestigationFingerprint.workspace_id == workspace_id,
            InvestigationFingerprint.fingerprint_id.in_(own_ids),
        )
    ).all()
    for candidate, fingerprint_id, role, category, kind in links:
        if kind != "exact":
            # The same generic line in two logs is a similarity, never a recurrence.
            offer(candidate, SIMILAR_TEXT, "similar_text", category)
            continue
        same = role == "primary" and own_ids[fingerprint_id] == "primary"
        offer(
            candidate,
            SAME_FAILURE if same else RELATED,
            "same_failure" if same else "related",
            category,
        )

    primary = next((fp for fp, role in own if role == "primary"), None)
    if primary is not None and (query := _or_query(f"{primary.subject} {primary.template}")):
        tsquery = func.to_tsquery(text("'simple'::regconfig"), query)
        rank = func.ts_rank_cd(FailureFingerprint.tsv, tsquery)
        rows = session.execute(
            select(InvestigationFingerprint.investigation_id, FailureFingerprint.category, rank)
            .join(
                FailureFingerprint, FailureFingerprint.id == InvestigationFingerprint.fingerprint_id
            )
            .where(
                FailureFingerprint.workspace_id == workspace_id,
                FailureFingerprint.version == FINGERPRINT_VERSION,
                FailureFingerprint.tsv.op("@@")(tsquery),
                FailureFingerprint.id != primary.id,
                InvestigationFingerprint.role == "primary",
            )
            .order_by(rank.desc())
            .limit(TEXT_CANDIDATES)
        ).all()
        top = max((float(r[2]) for r in rows), default=0.0) or 1.0
        for candidate, category, value in rows:
            offer(candidate, round(SIMILAR_TEXT * float(value) / top, 4), "similar_text", category)

    if not best:
        return []
    details = session.execute(
        select(
            Investigation.id,
            Investigation.title,
            Investigation.created_at,
            Diagnosis.category,
            Diagnosis.verification_status,
        )
        .outerjoin(Diagnosis, Diagnosis.investigation_id == Investigation.id)
        .where(Investigation.id.in_(best), Investigation.workspace_id == workspace_id)
    ).all()
    found: list[SimilarFailure] = []
    for inv_id, title, created_at, diag_category, status in details:
        earlier = created_at < current
        if earlier_only and not earlier:
            continue
        resolution = current_resolution(session, inv_id)
        if resolution is not None:
            provenance = "human_confirmed"
        elif status == "corroborated":
            provenance = "verifier_corroborated"
        elif status is not None:
            provenance = "model_hypothesis"
        else:
            provenance = "none"
        score, match, category = best[inv_id]
        found.append(
            SimilarFailure(
                investigation_id=inv_id,
                title=title,
                created_at=created_at,
                match=match,
                score=score,
                earlier=earlier,
                category=category,
                diagnosis_category=diag_category,
                verification_status=status,
                provenance=provenance,
                resolution=resolution.summary if resolution is not None else None,
            )
        )
    found.sort(key=lambda s: (-s.score, -s.created_at.timestamp()))
    return found[:limit]
