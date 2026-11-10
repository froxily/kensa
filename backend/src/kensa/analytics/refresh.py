"""Incremental, idempotent refresh of ``analytics_daily`` (v1.1, D-055).

A refresh recomputes whole days: it deletes a day's rows and inserts them again from the source
tables in one transaction, so refreshing the same day twice gives the same rows (idempotent),
and only days whose sources changed need refreshing (incremental):

* **CI runs:** a history sync refreshes the days of the runs it touched.
* **Investigations:** the days of investigations created or finished since the workspace's last
  refresh (``analytics_watermarks``).

Origins are kept apart (D-051): ``github_live`` and ``pasted`` are real observations;
``sample``, ``eval_synthetic`` and ``replay`` are not, and the dashboard leaves them out unless
asked.
"""

import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from kensa.db.models import AnalyticsWatermark

REAL_ORIGINS = ("github_live", "pasted")
ALL_ORIGINS = ("github_live", "pasted", "sample", "eval_synthetic", "replay")

_LOCK = text("SELECT pg_advisory_xact_lock(hashtext(:key))")
_DELETE = text("DELETE FROM analytics_daily WHERE workspace_id = :ws AND day = ANY(:days)")

_INSERT_CI = text(
    """
    INSERT INTO analytics_daily (
        id, workspace_id, day, source, repository, workflow, category, data_origin,
        runs, failed_runs, investigations, corroborated, latency_p50_ms, latency_p95_ms,
        refreshed_at
    )
    SELECT gen_random_uuid(), r.workspace_id, (r.gh_created_at AT TIME ZONE 'UTC')::date, 'ci',
           t.owner || '/' || t.repo, r.workflow_path, '', r.data_origin,
           count(*) FILTER (WHERE r.status = 'completed'),  -- runs with an outcome
           count(*) FILTER (WHERE r.status = 'completed' AND r.conclusion IN
               ('failure', 'timed_out', 'startup_failure', 'cancelled')),
           0, 0, NULL, NULL, now()
    FROM ci_runs r JOIN tracked_repositories t ON t.id = r.tracked_repository_id
    WHERE r.workspace_id = :ws AND (r.gh_created_at AT TIME ZONE 'UTC')::date = ANY(:days)
    GROUP BY 2, 3, 4, 5, 6, 7, 8  -- every key column (1 is the new row id)
    """
)

_INSERT_INVESTIGATIONS = text(
    """
    INSERT INTO analytics_daily (
        id, workspace_id, day, source, repository, workflow, category, data_origin,
        runs, failed_runs, investigations, corroborated, latency_p50_ms, latency_p95_ms,
        refreshed_at
    )
    SELECT gen_random_uuid(), i.workspace_id, (i.created_at AT TIME ZONE 'UTC')::date,
           'investigation',
           COALESCE(w.owner || '/' || w.repo, ''), COALESCE(w.workflow_path, ''),
           COALESCE(d.category, i.rule_category, 'unknown'),
           CASE i.source WHEN 'github' THEN 'github_live' WHEN 'sample' THEN 'sample'
                ELSE 'pasted' END,
           0, 0, count(*),
           count(*) FILTER (WHERE d.verification_status = 'corroborated'),
           (percentile_cont(0.5) WITHIN GROUP (ORDER BY
               EXTRACT(EPOCH FROM (i.finished_at - i.created_at)) * 1000)
               FILTER (WHERE i.finished_at IS NOT NULL))::integer,
           (percentile_cont(0.95) WITHIN GROUP (ORDER BY
               EXTRACT(EPOCH FROM (i.finished_at - i.created_at)) * 1000)
               FILTER (WHERE i.finished_at IS NOT NULL))::integer,
           now()
    FROM investigations i
    LEFT JOIN workflow_runs w ON w.investigation_id = i.id
    LEFT JOIN diagnoses d ON d.investigation_id = i.id
    WHERE i.workspace_id = :ws AND (i.created_at AT TIME ZONE 'UTC')::date = ANY(:days)
    GROUP BY 2, 3, 4, 5, 6, 7, 8  -- every key column (1 is the new row id)
    """
)

_DIRTY_INVESTIGATION_DAYS = text(
    """
    SELECT DISTINCT (created_at AT TIME ZONE 'UTC')::date FROM investigations
    WHERE workspace_id = :ws
      AND (CAST(:since AS timestamptz) IS NULL OR updated_at >= :since OR created_at >= :since)
    """
)


def refresh_days(session: Session, workspace_id: uuid.UUID, days: Iterable[date]) -> int:
    """Recompute these days completely. Returns how many days were refreshed."""
    wanted = sorted(set(days))
    if not wanted:
        return 0
    params = {"ws": workspace_id, "days": wanted}
    # One refresh per workspace at a time: the lock is held until this transaction ends.
    session.execute(_LOCK, {"key": f"analytics:{workspace_id}"})
    session.execute(_DELETE, params)
    session.execute(_INSERT_CI, params)
    session.execute(_INSERT_INVESTIGATIONS, params)
    return len(wanted)


def refresh_changed(session: Session, workspace_id: uuid.UUID, extra: Iterable[date] = ()) -> int:
    """Refresh the days of investigations changed since the last refresh, plus ``extra``."""
    watermark = session.get(AnalyticsWatermark, workspace_id)
    since = watermark.refreshed_at if watermark is not None else None
    started = datetime.now(UTC)
    days = set(
        session.execute(_DIRTY_INVESTIGATION_DAYS, {"ws": workspace_id, "since": since}).scalars()
    )
    if since is None:
        days |= set(
            session.execute(
                text(
                    "SELECT DISTINCT (gh_created_at AT TIME ZONE 'UTC')::date FROM ci_runs "
                    "WHERE workspace_id = :ws"
                ),
                {"ws": workspace_id},
            ).scalars()
        )
    days |= set(extra)
    count = refresh_days(session, workspace_id, days)
    session.execute(
        pg_insert(AnalyticsWatermark)
        .values(workspace_id=workspace_id, refreshed_at=started)
        .on_conflict_do_update(index_elements=["workspace_id"], set_={"refreshed_at": started})
    )
    return count


def run_days(session: Session, workspace_id: uuid.UUID, batch_id: uuid.UUID) -> set[date]:
    """The days of the runs one history sync touched."""
    return set(
        session.execute(
            text(
                "SELECT DISTINCT (gh_created_at AT TIME ZONE 'UTC')::date FROM ci_runs "
                "WHERE workspace_id = :ws AND batch_id = :batch"
            ),
            {"ws": workspace_id, "batch": batch_id},
        ).scalars()
    )
