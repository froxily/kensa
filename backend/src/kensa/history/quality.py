"""Data-quality checks over CI history and investigations (v1.1, D-052).

Each check is one SQL query that returns the problems it finds now. ``run_checks`` reconciles
them with ``dq_findings``: a new problem is inserted, a known one gets ``last_seen`` updated (and
is reopened if it had been resolved), and a stored problem the check no longer finds is marked
resolved. Every finding is tied to a tracked repository or an investigation, so purging either
removes its findings too (D-052, Forget repository).
"""

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from kensa.db.models import DqFinding


@dataclass(frozen=True)
class Check:
    name: str
    severity: str
    sql: str  # columns: entity_key, detail, tracked_repository_id, investigation_id


CHECKS: tuple[Check, ...] = (
    Check(
        "duplicate_import",
        "warning",
        """
        SELECT 'job:' || owner || '/' || repo || '#' || run_id || '.' || run_attempt || ':'
                   || job_id AS entity_key,
               'This job attempt was imported ' || count(*) || ' times.' AS detail,
               NULL::uuid AS tracked_repository_id,
               (array_agg(investigation_id ORDER BY created_at))[1] AS investigation_id
        FROM workflow_runs WHERE workspace_id = :ws
        GROUP BY owner, repo, run_id, run_attempt, job_id HAVING count(*) > 1
        """,
    ),
    Check(
        "failed_run_without_jobs",
        "warning",
        """
        SELECT 'run:' || r.run_id || '.' || r.run_attempt AS entity_key,
               'A failed run attempt has no jobs stored.' AS detail,
               r.tracked_repository_id, NULL::uuid AS investigation_id
        FROM ci_runs r
        WHERE r.workspace_id = :ws AND r.jobs_synced
          AND r.conclusion IN ('failure', 'timed_out', 'startup_failure', 'cancelled')
          AND NOT EXISTS (SELECT 1 FROM ci_jobs j WHERE j.ci_run_id = r.id)
        """,
    ),
    Check(
        "run_missing_timestamps",
        "warning",
        """
        SELECT 'run:' || run_id || '.' || run_attempt AS entity_key,
               'A completed run attempt has no start or update time.' AS detail,
               tracked_repository_id, NULL::uuid AS investigation_id
        FROM ci_runs
        WHERE workspace_id = :ws AND status = 'completed'
          AND (run_started_at IS NULL OR gh_updated_at IS NULL)
        """,
    ),
    Check(
        "job_missing_timestamps",
        "warning",
        """
        SELECT 'job:' || j.job_id AS entity_key,
               'A finished job has no start or completion time.' AS detail,
               r.tracked_repository_id, NULL::uuid AS investigation_id
        FROM ci_jobs j JOIN ci_runs r ON r.id = j.ci_run_id
        WHERE j.workspace_id = :ws AND j.conclusion IS NOT NULL
          AND (j.started_at IS NULL OR j.completed_at IS NULL)
        """,
    ),
    Check(
        "time_order",
        "error",
        """
        SELECT 'job:' || j.job_id AS entity_key,
               'A job completed before it started.' AS detail,
               r.tracked_repository_id, NULL::uuid AS investigation_id
        FROM ci_jobs j JOIN ci_runs r ON r.id = j.ci_run_id
        WHERE j.workspace_id = :ws AND j.completed_at < j.started_at
        UNION ALL
        SELECT 'run:' || run_id || '.' || run_attempt,
               'A run attempt was updated before it was created.',
               tracked_repository_id, NULL::uuid
        FROM ci_runs WHERE workspace_id = :ws AND gh_updated_at < gh_created_at
        """,
    ),
    Check(
        "classification_disagreement",
        "info",
        """
        SELECT 'investigation:' || i.id AS entity_key,
               'The rules suggested ' || i.rule_category || ', the diagnosis says '
                   || d.category || '.' AS detail,
               NULL::uuid AS tracked_repository_id, i.id AS investigation_id
        FROM investigations i JOIN diagnoses d ON d.investigation_id = i.id
        WHERE i.workspace_id = :ws AND i.rule_category IS NOT NULL
          AND i.rule_category <> 'unknown' AND d.category <> 'unknown'
          AND i.rule_category <> d.category
        """,
    ),
    Check(
        "fingerprint_category_conflict",
        "info",
        """
        SELECT 'fingerprint:' || f.hash AS entity_key,
               'Investigations sharing one fingerprint were diagnosed as '
                   || string_agg(DISTINCT d.category, ', ') || '.' AS detail,
               NULL::uuid AS tracked_repository_id,
               (array_agg(l.investigation_id ORDER BY l.created_at))[1] AS investigation_id
        FROM failure_fingerprints f
        JOIN investigation_fingerprints l ON l.fingerprint_id = f.id AND l.role = 'primary'
            AND f.kind = 'exact'
        JOIN diagnoses d ON d.investigation_id = l.investigation_id
        WHERE f.workspace_id = :ws AND d.category <> 'unknown'
        GROUP BY f.hash HAVING count(DISTINCT d.category) > 1
        """,
    ),
    Check(
        "listing_truncated",
        "warning",
        """
        SELECT 'batch:' || b.id AS entity_key,
               'GitHub listed 1,000 runs for one window; older runs in it may be missing.'
                   AS detail,
               b.tracked_repository_id, NULL::uuid AS investigation_id
        FROM etl_batches b
        WHERE b.workspace_id = :ws AND (b.counts ->> 'listing_truncated') IS NOT NULL
        """,
    ),
)


def run_checks(session: Session, workspace_id: uuid.UUID) -> Counter[str]:
    """Run every check and reconcile ``dq_findings``. Returns the open findings per check."""
    now = datetime.now(UTC)
    open_counts: Counter[str] = Counter()
    for check in CHECKS:
        rows = session.execute(text(check.sql), {"ws": workspace_id}).all()
        keys = [row.entity_key for row in rows]
        for row in rows:
            stmt = pg_insert(DqFinding).values(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                tracked_repository_id=row.tracked_repository_id,
                investigation_id=row.investigation_id,
                check=check.name,
                severity=check.severity,
                entity_key=str(row.entity_key)[:300],
                detail=str(row.detail)[:500],
            )
            session.execute(
                stmt.on_conflict_do_update(
                    constraint="uq_dq_findings_entity",
                    set_={"last_seen": now, "resolved_at": None, "detail": stmt.excluded.detail},
                )
            )
        resolve = update(DqFinding).where(
            DqFinding.workspace_id == workspace_id,
            DqFinding.check == check.name,
            DqFinding.resolved_at.is_(None),
        )
        if keys:
            resolve = resolve.where(DqFinding.entity_key.not_in([k[:300] for k in keys]))
        session.execute(resolve.values(resolved_at=now))
        open_counts[check.name] = len(rows)
    return open_counts
