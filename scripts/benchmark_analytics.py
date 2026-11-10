"""Analytics load benchmark (v1.1, D-055): refresh time and dashboard latency at scale.

    uv run --directory backend --no-sync python ../scripts/benchmark_analytics.py

Seeds a dedicated local database (``kensa_bench_analytics``) with SYNTHETIC rows only: 50,000 CI
runs, 250,000 jobs, 5,000 investigations with diagnoses, 500 recurring fingerprints, over 365
days and 5 repositories. Nothing here touches the working database or the network. Measures:

* a full refresh of every day, run twice (the second must give identical rows: idempotency);
* an incremental refresh after one investigation changes (only its day is recomputed);
* the dashboard endpoint's latency (p50/p95) over a mix of filters, through the real API, with
  history matching off (the default) and on (which adds the recurring-failure query);
* storage per row.

Writes ``eval/reports/v11-analytics-benchmark.md`` and ``.jsonl``.
"""

import json
import platform
import statistics
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from e2e_server import prepare_database
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from kensa.analysis.fingerprint import FINGERPRINT_VERSION
from kensa.analytics.refresh import refresh_changed, refresh_days
from kensa.app import create_app
from kensa.core.config import Settings
from kensa.db.models import DEFAULT_WORKSPACE_ID
from kensa.db.session import build_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS = REPO_ROOT / "eval" / "reports"
DB = "kensa_bench_analytics"
RUNS, JOBS_PER_RUN, INVESTIGATIONS, FINGERPRINTS, DAYS = 50_000, 5, 5_000, 500, 365
TARGET_P95_MS = 300
WS = str(DEFAULT_WORKSPACE_ID)

SEED = [
    """INSERT INTO tracked_repositories (id, workspace_id, owner, repo, history_days)
       SELECT gen_random_uuid(), :ws, 'bench-org', 'repo-' || r, 365
       FROM generate_series(0, 4) r""",
    """INSERT INTO ci_runs (id, workspace_id, tracked_repository_id, run_id, run_attempt,
           run_number, workflow_id, workflow_path, workflow_name, event, head_branch, head_sha,
           status, conclusion, gh_created_at, jobs_synced, data_origin)
       SELECT gen_random_uuid(), :ws, t.id, 9000000 + i, 1, i,
              100 + (i / 5) % 4, '.github/workflows/w' || ((i / 5) % 4) || '.yml',
              'Workflow ' || ((i / 5) % 4),
              CASE WHEN i % 3 = 0 THEN 'pull_request' ELSE 'push' END, 'main',
              substr(md5(i::text) || md5((i + 1)::text), 1, 40), 'completed',
              CASE WHEN i % 7 = 0 THEN 'failure' WHEN i % 41 = 0 THEN 'cancelled'
                   ELSE 'success' END,
              now() - make_interval(days => i % :days, mins => i % 1440), true, 'github_live'
       FROM generate_series(1, :runs) i
       JOIN (SELECT id, row_number() OVER (ORDER BY repo) - 1 AS n FROM tracked_repositories) t
         ON t.n = i % 5""",
    """INSERT INTO ci_jobs (id, workspace_id, ci_run_id, job_id, name, status, conclusion,
           started_at, completed_at, labels)
       SELECT gen_random_uuid(), :ws, r.id, r.run_id * 10 + j, 'job-' || j, 'completed',
              CASE WHEN r.conclusion = 'failure' AND j = 1 THEN 'failure' ELSE 'success' END,
              r.gh_created_at, r.gh_created_at + make_interval(secs => 30 + j * 7),
              ARRAY['ubuntu-24.04']
       FROM ci_runs r CROSS JOIN generate_series(1, :jobs) j""",
    """INSERT INTO investigations (id, workspace_id, title, source, status, provider, created_at,
           updated_at, finished_at, rule_category)
       SELECT gen_random_uuid(), :ws, 'bench ' || i,
              CASE WHEN i % 5 < 3 THEN 'github' ELSE 'paste' END, 'completed', 'mock',
              now() - make_interval(days => i % :days, mins => i % 1440),
              now() - make_interval(days => i % :days, mins => i % 1440),
              now() - make_interval(days => i % :days, mins => i % 1440)
                    + make_interval(secs => 20 + i % 40),
              (ARRAY['missing_env_var', 'dependency_build', 'test_regression', 'docker',
                     'oom_timeout'])[1 + i % 5]
       FROM generate_series(1, :investigations) i""",
    """INSERT INTO diagnoses (id, workspace_id, investigation_id, category, summary, root_cause,
           confidence, uncertainty, recommended_fixes, verification_status, verification_notes,
           provider)
       SELECT gen_random_uuid(), :ws, i.id, i.rule_category, 'synthetic', 'synthetic', 0.5, '',
              ARRAY[]::text[],
              CASE WHEN row_number() OVER (ORDER BY i.id) % 5 < 2 THEN 'corroborated'
                   ELSE 'plausible' END,
              ARRAY[]::text[], 'mock'
       FROM investigations i""",
    """INSERT INTO workflow_runs (id, workspace_id, investigation_id, owner, repo, run_id,
           run_number, run_attempt, workflow_name, workflow_path, event, head_sha, html_url,
           job_id, job_name, job_html_url, log_source)
       SELECT gen_random_uuid(), :ws, i.id, 'bench-org', 'repo-' || (n % 5), 8000000 + n, n, 1,
              'Workflow ' || (n % 4), '.github/workflows/w' || (n % 4) || '.yml', 'push',
              substr(md5(n::text) || md5(n::text), 1, 40), 'https://github.com/bench', 7000000 + n,
              'job-1', 'https://github.com/bench', 'github'
       FROM (SELECT id, row_number() OVER (ORDER BY id) AS n FROM investigations
             WHERE source = 'github') i""",
    # The current fingerprint version, exact: the recurring-failure query counts only those.
    """INSERT INTO failure_fingerprints (id, workspace_id, version, hash, category, rule_id,
           subject, template, kind)
       SELECT gen_random_uuid(), :ws, :fp_version, md5('fp' || f) || md5('fp2' || f),
              'dependency_build', 'bench.rule', 'subject-' || f, 'synthetic template ' || f,
              'exact'
       FROM generate_series(1, :fingerprints) f""",
    """INSERT INTO investigation_fingerprints (id, workspace_id, investigation_id, fingerprint_id,
           role)
       SELECT gen_random_uuid(), :ws, i.id, f.id, 'primary'
       FROM (SELECT id, row_number() OVER (ORDER BY id) % :fingerprints AS k FROM investigations) i
       JOIN (SELECT id, row_number() OVER (ORDER BY id) % :fingerprints AS k
             FROM failure_fingerprints) f ON f.k = i.k""",
]

DAILY_KEY = (
    "SELECT day, source, repository, workflow, category, data_origin, runs, failed_runs, "
    "investigations, corroborated, latency_p50_ms, latency_p95_ms FROM analytics_daily "
    "ORDER BY 1, 2, 3, 4, 5, 6"
)


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def main() -> int:
    base = Settings(inference_provider="mock", embedding_provider="mock", worker_enabled=False)
    url = prepare_database(base, DB)
    settings = Settings(
        database_url=url, inference_provider="mock", embedding_provider="mock", worker_enabled=False
    )
    engine = build_engine(settings)
    params = {
        "ws": WS,
        "runs": RUNS,
        "jobs": JOBS_PER_RUN,
        "investigations": INVESTIGATIONS,
        "fingerprints": FINGERPRINTS,
        "days": DAYS,
        "fp_version": FINGERPRINT_VERSION,
    }
    results: dict[str, Any] = {}
    started = time.perf_counter()
    with engine.begin() as conn:
        for statement in SEED:
            conn.execute(text(statement), params)
        conn.execute(text("ANALYZE"))
    results["seed_seconds"] = round(time.perf_counter() - started, 1)
    with engine.connect() as conn:
        counts = {
            table: int(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar() or 0)  # noqa: S608
            for table in ("ci_runs", "ci_jobs", "investigations", "investigation_fingerprints")
        }
    results["rows"] = counts

    all_days = [(datetime.now(UTC) - timedelta(days=d)).date() for d in range(DAYS + 2)]
    timings = []
    snapshots = []
    refreshed = 0
    for _ in range(2):
        started = time.perf_counter()
        with Session(engine) as session, session.begin():
            refreshed = refresh_days(session, DEFAULT_WORKSPACE_ID, all_days)
        timings.append(time.perf_counter() - started)
        with engine.connect() as conn:
            snapshots.append([tuple(r) for r in conn.execute(text(DAILY_KEY)).all()])
    results["full_refresh_days"] = refreshed
    results["full_refresh_seconds"] = [round(t, 2) for t in timings]
    results["refresh_idempotent"] = snapshots[0] == snapshots[1]
    results["analytics_daily_rows"] = len(snapshots[1])

    with Session(engine) as session, session.begin():
        refresh_changed(session, DEFAULT_WORKSPACE_ID)  # set the watermark
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE investigations SET updated_at = now() WHERE id = "
                "(SELECT id FROM investigations ORDER BY created_at DESC LIMIT 1)"
            )
        )
    started = time.perf_counter()
    with Session(engine) as session, session.begin():
        incremental = refresh_changed(session, DEFAULT_WORKSPACE_ID)
    results["incremental_refresh_days"] = incremental
    results["incremental_refresh_ms"] = round((time.perf_counter() - started) * 1000, 1)

    filters = [
        {"days": d, **({"repository": "bench-org/repo-1"} if r else {}), "include_all_origins": a}
        for d in (7, 30, 90, 365)
        for r in (False, True)
        for a in (False, True)
    ]
    measured: dict[str, list[float]] = {}
    full_year: dict[str, Any] = {}
    # Off is the default (D-057); on adds the recurring-failure query, the slower case.
    for mode, matching in (("off", False), ("on", True)):
        app_settings = settings.model_copy(update={"history_matching": matching})
        client = TestClient(create_app(app_settings), base_url="http://127.0.0.1")
        latencies: list[float] = []
        client.get("/api/analytics/dashboard", params={"days": 30})  # warm-up, not counted
        for _ in range(3):
            for f in filters:
                started = time.perf_counter()
                response = client.get("/api/analytics/dashboard", params=f)
                latencies.append((time.perf_counter() - started) * 1000)
                if response.status_code != 200:
                    print(response.status_code, response.text[:300])
                    return 1
        measured[mode] = latencies
        full_year = client.get("/api/analytics/dashboard", params={"days": 365}).json()
    for mode, latencies in measured.items():
        results[f"dashboard_{mode}_requests"] = len(latencies)
        results[f"dashboard_{mode}_p50_ms"] = round(statistics.median(latencies), 1)
        results[f"dashboard_{mode}_p95_ms"] = round(percentile(latencies, 0.95), 1)
        results[f"dashboard_{mode}_max_ms"] = round(max(latencies), 1)
    results["dashboard_target_p95_ms"] = TARGET_P95_MS
    results["dashboard_meets_target"] = all(
        results[f"dashboard_{mode}_p95_ms"] < TARGET_P95_MS for mode in measured
    )
    results["year_summary"] = full_year["summary"]

    with engine.connect() as conn:
        sizes = {
            table: int(
                conn.execute(text(f"SELECT pg_total_relation_size('{table}')")).scalar() or 0
            )
            for table in ("ci_runs", "ci_jobs", "analytics_daily", "investigations")
        }
        results["database_bytes"] = conn.execute(
            text("SELECT pg_database_size(current_database())")
        ).scalar()
    results["bytes_per_row"] = {
        "ci_runs": round(sizes["ci_runs"] / counts["ci_runs"]),
        "ci_jobs": round(sizes["ci_jobs"] / counts["ci_jobs"]),
    }
    results["table_bytes"] = sizes
    engine.dispose()

    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "v11-analytics-benchmark.jsonl").write_text(
        json.dumps(results, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    lines = [
        "# Analytics load benchmark (v1.1)",
        "",
        "> Generated by `scripts/benchmark_analytics.py` on SYNTHETIC rows in a dedicated local "
        "database (`kensa_bench_analytics`). Real measurements on this machine; they show how "
        "the aggregate and the dashboard scale, not anything about real CI data.",
        "",
        f"- **Date (UTC):** {datetime.now(UTC):%Y-%m-%d %H:%M} · **OS:** {platform.platform()} · "
        "**Database:** PostgreSQL in the local Compose container (1 GB memory limit)",
        f"- **Rows:** {counts['ci_runs']:,} runs, {counts['ci_jobs']:,} jobs, "
        f"{counts['investigations']:,} investigations over {DAYS} days, 5 repositories",
        "",
        "| measure | result |",
        "|---|---|",
        f"| seeding | {results['seed_seconds']} s |",
        f"| full refresh of {refreshed} days (two runs) | "
        f"{' s, '.join(str(t) for t in results['full_refresh_seconds'])} s |",
        f"| second full refresh gives identical rows | {results['refresh_idempotent']} |",
        f"| `analytics_daily` rows | {results['analytics_daily_rows']:,} |",
        f"| incremental refresh after one investigation changed | "
        f"{incremental} day, {results['incremental_refresh_ms']} ms |",
        *(
            f"| dashboard API, history matching {mode}, "
            f"{results[f'dashboard_{mode}_requests']} requests over {len(filters)} filter mixes | "
            f"p50 {results[f'dashboard_{mode}_p50_ms']} ms · "
            f"p95 {results[f'dashboard_{mode}_p95_ms']} ms · "
            f"max {results[f'dashboard_{mode}_max_ms']} ms |"
            for mode in measured
        ),
        f"| target: dashboard p95 < {TARGET_P95_MS} ms in both modes | "
        f"{'met' if results['dashboard_meets_target'] else 'NOT met'} |",
        f"| storage per row | runs {results['bytes_per_row']['ci_runs']} B · jobs "
        f"{results['bytes_per_row']['ci_jobs']} B (tables with indexes) |",
        f"| database size | {results['database_bytes'] / 1e6:.0f} MB |",
        "",
        "The dashboard latency includes its own `refresh_changed` check on every request, as "
        "in production.",
        "",
    ]
    (REPORTS / "v11-analytics-benchmark.md").write_text(
        "\n".join(lines), encoding="utf-8", newline="\n"
    )
    print(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
