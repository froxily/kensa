"""Persisting a change analysis and turning it into prompt notes (v1.1, D-054).

A suspect's hunks become a ``diff`` document of the investigation, redacted and chunked per hunk,
so the model can cite changed lines as supporting evidence. They can never corroborate a cause:
the verifier accepts only causes the log itself states (D-040, D-046).

The prompt sees a suspect only as one of Kensa's own findings: a sanitised path, a kind and the
names of the signals that matched, never text copied from a commit or a diff.
"""

import hashlib
import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from kensa.changes.analyzer import RUNNER_IMAGE, ChangeAnalysis
from kensa.db.models import ChangeAnalysisRecord, ChangeSuspect, Chunk, Document
from kensa.ingestion.redaction import redact

NOTE_SUSPECTS = 3
_SAFE_PATH = re.compile(r"[^\w./@+-]")

SIGNAL_WORDS = {
    "in_log": "its path appears near a failure line",
    "subject_in_diff": "a changed line names what failed",
    "kind_matches_category": "its kind fits the failure",
    "mentioned_in_log": "the log mentions it",
    "runner_image_changed": "the runner image changed",
    "image_fits_category": "image changes often cause this kind of failure",
}


def safe_path(path: str) -> str:
    return _SAFE_PATH.sub("_", path)[:160]


def _diff_document(
    session: Session,
    workspace_id: uuid.UUID,
    investigation_id: uuid.UUID,
    path: str,
    hunks: list[str],
) -> uuid.UUID:
    texts = [redact(h).text for h in hunks]
    content = "\n".join(texts)
    data = content.encode("utf-8")
    document = Document(
        workspace_id=workspace_id,
        investigation_id=investigation_id,
        source_type="diff",
        name=f"diff/{path}"[:255],
        content=content,
        content_hash=hashlib.sha256(data).hexdigest(),
        byte_size=len(data),
        line_count=content.count("\n") + 1,
    )
    session.add(document)
    session.flush()
    line = 1
    for ordinal, hunk in enumerate(texts):
        count = hunk.count("\n") + 1
        session.add(
            Chunk(
                workspace_id=workspace_id,
                document_id=document.id,
                ordinal=ordinal,
                kind="diff_hunk",
                start_line=line,
                end_line=line + count - 1,
                content=hunk,
                content_hash=hashlib.sha256(hunk.encode("utf-8")).hexdigest(),
            )
        )
        line += count
    return document.id


def save_analysis(
    session: Session,
    workspace_id: uuid.UUID,
    investigation_id: uuid.UUID,
    failed_sha: str,
    analysis: ChangeAnalysis,
    *,
    diff_evidence: bool = True,
) -> ChangeAnalysisRecord:
    comparison = analysis.comparison
    record = ChangeAnalysisRecord(
        workspace_id=workspace_id,
        investigation_id=investigation_id,
        comparability=analysis.comparability,
        reasons=[r[:300] for r in analysis.reasons][:10],
        factors=[
            {"name": f.name, "state": f.state, "detail": f.detail[:200]} for f in analysis.factors
        ],
        unverified=analysis.unverified,
        baseline_run_id=analysis.baseline.run_id if analysis.baseline else None,
        baseline_sha=analysis.baseline.head_sha if analysis.baseline else None,
        failed_sha=failed_sha,
        compare_status=comparison.status if comparison else None,
        commits=len(comparison.commits) if comparison else 0,
        files=len(comparison.files) if comparison else 0,
        truncated=bool(comparison.truncated) if comparison else False,
    )
    session.add(record)
    session.flush()
    for suspect in analysis.suspects:
        document_id = None
        if diff_evidence and suspect.hunks and suspect.path != RUNNER_IMAGE:
            document_id = _diff_document(
                session, workspace_id, investigation_id, suspect.path, suspect.hunks
            )
        session.add(
            ChangeSuspect(
                workspace_id=workspace_id,
                analysis_id=record.id,
                rank=suspect.rank,
                path=suspect.path[:500],
                change_kind=suspect.change_kind,
                score=suspect.score,
                status=suspect.status,
                signals=suspect.signals,
                document_id=document_id,
            )
        )
    session.flush()
    return record


def load_analysis(
    session: Session, investigation_id: uuid.UUID
) -> tuple[ChangeAnalysisRecord, list[ChangeSuspect]] | None:
    record = session.execute(
        select(ChangeAnalysisRecord).where(
            ChangeAnalysisRecord.investigation_id == investigation_id
        )
    ).scalar_one_or_none()
    if record is None:
        return None
    suspects = list(
        session.execute(
            select(ChangeSuspect)
            .where(ChangeSuspect.analysis_id == record.id)
            .order_by(ChangeSuspect.rank)
        ).scalars()
    )
    return record, suspects


def change_notes(record: ChangeAnalysisRecord, suspects: list[ChangeSuspect]) -> list[str]:
    """Kensa's own findings for the diagnosis prompt: sanitised paths and fixed wording only."""
    if record.comparability in ("no_baseline", "incomparable", "history_unavailable"):
        return [
            f"no comparable earlier successful run ({record.comparability.replace('_', ' ')}); "
            "do not assume what changed."
        ]
    if record.comparability == "identical":
        return [
            "the code is identical to the last successful run; a code change did not cause "
            "this, so consider the environment, a service, the runner or a flaky test."
        ]
    notes = []
    if record.comparability == "partially_comparable":
        notes.append(
            "the last successful run is only partly comparable ("
            + ", ".join(u.replace("_", " ") for u in record.unverified[:4])
            + ")."
        )
    named = []
    for suspect in suspects[:NOTE_SUSPECTS]:
        why = "; ".join(SIGNAL_WORDS[s] for s in suspect.signals if s in SIGNAL_WORDS)
        named.append(
            f"{safe_path(suspect.path)} ({suspect.change_kind.replace('_', ' ')}; "
            f"{suspect.status}: {why or 'no strong signal'})"
        )
    if named:
        notes.append(
            "changes since the last successful run, ranked by correlation with this failure "
            "(correlation is not proof; a diff can support a cause the log states, never prove "
            "it): " + ", ".join(named) + "."
        )
    return notes
