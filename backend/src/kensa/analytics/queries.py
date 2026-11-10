"""The dashboard's queries (v1.1, D-055). Every query is scoped to a workspace and filtered by
date range, repository, workflow and data origin; by default only real observations count.

The SQL is assembled only from this module's constant fragments; every value is a bound
parameter (hence the S608 exemption in pyproject.toml)."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from kensa.analysis.fingerprint import FINGERPRINT_VERSION
from kensa.analytics.refresh import REAL_ORIGINS


@dataclass(frozen=True)
class Filters:
    start: date
    end: date  # inclusive
    repository: str | None = None
    workflow: str | None = None
    origins: tuple[str, ...] = field(default=REAL_ORIGINS)

    @classmethod
    def last_days(cls, days: int, **kwargs: Any) -> "Filters":
        end = datetime.now(UTC).date()
        return cls(start=end - timedelta(days=days - 1), end=end, **kwargs)

    def params(self, workspace_id: uuid.UUID) -> dict[str, Any]:
        return {
            "ws": workspace_id,
            "start": self.start,
            "end": self.end,
            "repository": self.repository,
            "workflow": self.workflow,
            "origins": list(self.origins),
            # Recurring failures are exact fingerprints of the current version only (D-057).
            "fingerprint_version": FINGERPRINT_VERSION,
            # The same days as a timestamp range, so the investigations index can serve it.
            "start_at": datetime.combine(self.start, time.min, UTC),
            "end_at": datetime.combine(self.end + timedelta(days=1), time.min, UTC),
        }


_WHERE = """
    workspace_id = :ws AND day BETWEEN :start AND :end AND data_origin = ANY(:origins)
    AND (CAST(:repository AS text) IS NULL OR repository = :repository)
    AND (CAST(:workflow AS text) IS NULL OR workflow = :workflow)
"""
# Investigations (alias i) joined to their imported run (alias w), filtered the same way.
_INVESTIGATION_FILTER = """
    i.workspace_id = :ws
    AND i.created_at >= :start_at AND i.created_at < :end_at
    AND (CASE i.source WHEN 'github' THEN 'github_live' WHEN 'sample' THEN 'sample'
         ELSE 'pasted' END) = ANY(:origins)
    AND (CAST(:repository AS text) IS NULL OR w.owner || '/' || w.repo = :repository)
    AND (CAST(:workflow AS text) IS NULL OR w.workflow_path = :workflow)
"""
_INVESTIGATIONS = (
    "FROM investigations i LEFT JOIN workflow_runs w ON w.investigation_id = i.id WHERE "
    + _INVESTIGATION_FILTER
)


def _rows(session: Session, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(row._mapping) for row in session.execute(text(sql), params)]


def summary(session: Session, workspace_id: uuid.UUID, f: Filters) -> dict[str, Any]:
    p = f.params(workspace_id)
    totals = _rows(
        session,
        f"""
        SELECT COALESCE(sum(runs), 0) AS runs, COALESCE(sum(failed_runs), 0) AS failed_runs,
               COALESCE(sum(investigations), 0) AS investigations,
               COALESCE(sum(corroborated), 0) AS corroborated
        FROM analytics_daily WHERE {_WHERE}
        """,
        p,
    )[0]
    latency = _rows(
        session,
        f"""
        SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY
                   EXTRACT(EPOCH FROM (i.finished_at - i.created_at)))
                   FILTER (WHERE i.finished_at IS NOT NULL) AS p50,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY
                   EXTRACT(EPOCH FROM (i.finished_at - i.created_at)))
                   FILTER (WHERE i.finished_at IS NOT NULL) AS p95
        {_INVESTIGATIONS}
        """,
        p,
    )[0]
    recurring = session.execute(
        text(
            f"""
            SELECT count(*) FROM (
                SELECT l.fingerprint_id FROM investigation_fingerprints l
                JOIN failure_fingerprints fp ON fp.id = l.fingerprint_id
                    AND fp.kind = 'exact' AND fp.version = :fingerprint_version
                JOIN investigations i ON i.id = l.investigation_id
                LEFT JOIN workflow_runs w ON w.investigation_id = i.id
                WHERE l.role = 'primary' AND {_INVESTIGATION_FILTER}
                GROUP BY l.fingerprint_id HAVING count(*) > 1
            ) recurring
            """
        ),
        p,
    ).scalar_one()
    open_findings = session.execute(
        text("SELECT count(*) FROM dq_findings WHERE workspace_id = :ws AND resolved_at IS NULL"),
        p,
    ).scalar_one()
    runs, failed = int(totals["runs"]), int(totals["failed_runs"])
    investigations = int(totals["investigations"])
    return {
        "runs": runs,
        "failed_runs": failed,
        "failure_rate": round(failed / runs, 4) if runs else None,
        "investigations": investigations,
        "corroborated": int(totals["corroborated"]),
        "latency_p50_seconds": round(float(latency["p50"]), 1) if latency["p50"] else None,
        "latency_p95_seconds": round(float(latency["p95"]), 1) if latency["p95"] else None,
        "recurring_failures": int(recurring),
        "open_quality_findings": int(open_findings),
    }


def trends(session: Session, workspace_id: uuid.UUID, f: Filters) -> list[dict[str, Any]]:
    rows = {
        r["day"]: r
        for r in _rows(
            session,
            f"""
            SELECT day, sum(runs) AS runs, sum(failed_runs) AS failed_runs,
                   sum(investigations) AS investigations, sum(corroborated) AS corroborated
            FROM analytics_daily WHERE {_WHERE} GROUP BY day
            """,
            f.params(workspace_id),
        )
    }
    series = []
    day = f.start
    while day <= f.end:
        row = rows.get(day, {})
        series.append(
            {
                "day": day.isoformat(),
                "runs": int(row.get("runs") or 0),
                "failed_runs": int(row.get("failed_runs") or 0),
                "investigations": int(row.get("investigations") or 0),
                "corroborated": int(row.get("corroborated") or 0),
            }
        )
        day += timedelta(days=1)
    return series


def categories(session: Session, workspace_id: uuid.UUID, f: Filters) -> list[dict[str, Any]]:
    return _rows(
        session,
        f"""
        SELECT category, sum(investigations)::int AS investigations,
               sum(corroborated)::int AS corroborated
        FROM analytics_daily WHERE source = 'investigation' AND {_WHERE}
        GROUP BY category ORDER BY sum(investigations) DESC, category
        """,
        f.params(workspace_id),
    )


def workflows(session: Session, workspace_id: uuid.UUID, f: Filters) -> list[dict[str, Any]]:
    rows = _rows(
        session,
        f"""
        SELECT repository, workflow, sum(runs)::int AS runs,
               sum(failed_runs)::int AS failed_runs,
               sum(investigations)::int AS investigations
        FROM analytics_daily WHERE {_WHERE} AND repository <> ''
        GROUP BY repository, workflow ORDER BY sum(failed_runs) DESC, repository, workflow
        LIMIT 50
        """,
        f.params(workspace_id),
    )
    for row in rows:
        row["failure_rate"] = round(row["failed_runs"] / row["runs"], 4) if row["runs"] else None
    return rows


def recurring(session: Session, workspace_id: uuid.UUID, f: Filters) -> list[dict[str, Any]]:
    """Fingerprints seen in more than one investigation in the range (primary role)."""
    rows = _rows(
        session,
        f"""
        SELECT fp.hash, fp.category, fp.subject, fp.template,
               count(*)::int AS occurrences,
               min(i.created_at) AS first_seen, max(i.created_at) AS last_seen,
               (array_agg(i.id ORDER BY i.created_at DESC))[1:5] AS investigation_ids
        FROM investigation_fingerprints l
        JOIN failure_fingerprints fp ON fp.id = l.fingerprint_id
            AND fp.kind = 'exact' AND fp.version = :fingerprint_version
        JOIN investigations i ON i.id = l.investigation_id
        LEFT JOIN workflow_runs w ON w.investigation_id = i.id
        WHERE l.role = 'primary' AND {_INVESTIGATION_FILTER}
        GROUP BY fp.hash, fp.category, fp.subject, fp.template
        HAVING count(*) > 1
        ORDER BY count(*) DESC, max(i.created_at) DESC
        LIMIT 20
        """,
        f.params(workspace_id),
    )
    return rows


def freshness(session: Session, workspace_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = _rows(
        session,
        """
        SELECT t.id, t.owner || '/' || t.repo AS repository, t.last_sync_at,
               t.sync_state ->> 'complete_through' AS complete_through,
               (SELECT b.status FROM etl_batches b WHERE b.tracked_repository_id = t.id
                ORDER BY b.started_at DESC LIMIT 1) AS last_status
        FROM tracked_repositories t WHERE t.workspace_id = :ws ORDER BY t.owner, t.repo
        """,
        {"ws": workspace_id},
    )
    now = datetime.now(UTC)
    for row in rows:
        complete = row["complete_through"]
        moment = datetime.fromisoformat(complete.replace("Z", "+00:00")) if complete else None
        row["lag_hours"] = round((now - moment).total_seconds() / 3600, 1) if moment else None
    return rows


def quality(session: Session, workspace_id: uuid.UUID) -> list[dict[str, Any]]:
    return _rows(
        session,
        """
        SELECT "check", severity, count(*)::int AS open
        FROM dq_findings WHERE workspace_id = :ws AND resolved_at IS NULL
        GROUP BY "check", severity ORDER BY count(*) DESC, "check"
        """,
        {"ws": workspace_id},
    )


def options(session: Session, workspace_id: uuid.UUID) -> dict[str, list[str]]:
    rows = _rows(
        session,
        """
        SELECT DISTINCT repository, workflow FROM analytics_daily
        WHERE workspace_id = :ws AND repository <> '' ORDER BY repository, workflow
        """,
        {"ws": workspace_id},
    )
    return {
        "repositories": sorted({r["repository"] for r in rows}),
        "workflows": sorted({r["workflow"] for r in rows if r["workflow"]}),
    }
