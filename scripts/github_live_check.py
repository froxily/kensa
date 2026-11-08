"""M4 live check: investigate genuine failed GitHub Actions runs from public repositories.

Drives the real API in-process (``TestClient``, with the real background worker): look up the
run, import the failed job (log, workflow file and referenced source files at the run's commit),
then let the agent diagnose it with the local Ollama model. Writes
``eval/reports/m4-live-github.md`` plus raw JSONL. Uses the development database from ``.env``,
so the investigations can be opened in the UI afterwards; they stop at the approval step, and
the decision is left to the owner.

Needs the owner's read-only ``KENSA_GITHUB_TOKEN`` (GitHub serves job logs only to signed-in
requests). The token is never printed or written anywhere. Reads from GitHub only.

    uv run --directory backend --no-sync python ../scripts/github_live_check.py <run-or-job-url> ...
"""

import argparse
import json
import platform
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from benchmark_model import git_sha, gpu_description
from fastapi.testclient import TestClient

from kensa.app import create_app
from kensa.core.config import Settings
from kensa.inference.ollama import normalize_model_name

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT = REPO_ROOT / "eval" / "reports" / "m4-live-github.md"
SETTLED = {"awaiting_approval", "completed", "failed"}


class PlacementSampler:
    """Polls Ollama's /api/ps and records how much of the LLM sat in VRAM while it ran."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.samples: list[tuple[int, int, int]] = []  # (llm size MiB, llm in VRAM MiB, models)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self) -> None:
        with httpx.Client(base_url=self.settings.ollama_base_url, timeout=5) as client:
            while not self._stop.is_set():
                try:
                    models = client.get("/api/ps").json().get("models", [])
                except (httpx.HTTPError, ValueError):
                    models = []
                for entry in models:
                    name = normalize_model_name(str(entry.get("name")))
                    if name == normalize_model_name(self.settings.llm_model):
                        self.samples.append(
                            (
                                int(entry["size"]) // 2**20,
                                int(entry["size_vram"]) // 2**20,
                                len(models),
                            )
                        )
                self._stop.wait(1.0)

    def __enter__(self) -> "PlacementSampler":
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def summary(self) -> dict[str, Any]:
        if not self.samples:
            return {"llm_seen": False}
        offloaded = [s for s in self.samples if s[1] < s[0]]
        return {
            "llm_seen": True,
            "llm_size_mib": self.samples[0][0],
            "min_llm_vram_mib": min(s[1] for s in self.samples),
            "samples": len(self.samples),
            "samples_partly_on_cpu": len(offloaded),
            "max_models_loaded_with_llm": max(s[2] for s in self.samples),
        }


@dataclass
class LiveRun:
    url: str
    repository: str
    run_id: int
    run_number: int
    run_attempt: int
    workflow: str
    head_sha: str
    job_id: int
    job_name: str
    failed_steps: list[str]
    import_seconds: float
    total_seconds: float
    status: str
    log_source: str = ""
    log_lines: int = 0
    log_dropped_lines: int = 0
    files_fetched: list[str] = field(default_factory=list)
    files_missing: list[str] = field(default_factory=list)
    category: str | None = None
    verification: str | None = None
    rule_category: str | None = None
    diagnosis_attempts: int | None = None
    citations_valid: int = 0
    citations_total: int = 0
    llm_ms: int | None = None
    summary: str = ""
    evidence_sources: dict[str, int] = field(default_factory=dict)
    repository_evidence_at_run_commit: bool | None = None
    proposals: int = 0
    proposals_with_diff: int = 0
    timeline: list[str] = field(default_factory=list)
    placement: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def investigate(client: TestClient, settings: Settings, url: str, provider: str) -> LiveRun:
    lookup = client.post("/api/github/lookup", json={"url": url})
    if lookup.status_code != 200:
        raise RuntimeError(f"lookup failed ({lookup.status_code}): {lookup.json().get('detail')}")
    found = lookup.json()
    if found["kind"] != "run" or not found["jobs"]:
        raise RuntimeError("the URL must name a failed run with a failed job")
    run = found["run"]
    job = next(j for j in found["jobs"] if j["id"] == found["selected_job_id"])
    target: dict[str, Any] = {
        "owner": found["owner"],
        "repo": found["repo"],
        "run_id": run["id"],
        "job_id": job["id"],
    }
    if found["attempt"]:
        target["attempt"] = found["attempt"]
    result = LiveRun(
        url=url,
        repository=f"{found['owner']}/{found['repo']}",
        run_id=run["id"],
        run_number=run["run_number"],
        run_attempt=run["run_attempt"],
        workflow=run["name"],
        head_sha=run["head_sha"],
        job_id=job["id"],
        job_name=job["name"],
        failed_steps=[s["name"] for s in job["failed_steps"]],
        import_seconds=0.0,
        total_seconds=0.0,
        status="not_started",
    )
    started = time.perf_counter()
    with PlacementSampler(settings) as sampler:
        created = client.post(
            "/api/investigations",
            json={"source": "github", "provider": provider, "github": target},
        )
        result.import_seconds = round(time.perf_counter() - started, 1)
        if created.status_code != 201:
            result.status, result.error = "import_failed", str(created.json().get("detail"))
            return result
        investigation_id = created.json()["id"]
        detail: dict[str, Any] = {}
        deadline = time.monotonic() + 1200
        while time.monotonic() < deadline:
            detail = client.get(f"/api/investigations/{investigation_id}").json()
            if detail["status"] in SETTLED:
                break
            time.sleep(2)
    result.total_seconds = round(time.perf_counter() - started, 1)
    result.placement = sampler.summary()
    result.status = detail.get("status", "unknown")

    github_run = detail.get("github_run") or {}
    result.log_source = github_run.get("log_source", "")
    result.log_dropped_lines = github_run.get("log_dropped_lines", 0)
    result.files_fetched = github_run.get("files_fetched", [])
    result.files_missing = github_run.get("files_missing", [])
    result.log_lines = sum(d["line_count"] for d in detail.get("documents", []))
    diagnosis = detail.get("diagnosis") or {}
    if diagnosis:
        result.category = diagnosis["category"]
        result.verification = diagnosis["verification_status"]
        result.rule_category = diagnosis["rule_category"]
        result.diagnosis_attempts = diagnosis["diagnosis_attempts"]
        result.citations_valid = sum(c["valid"] for c in diagnosis["citations"])
        result.citations_total = len(diagnosis["citations"])
        result.llm_ms = diagnosis["duration_ms"]
        established = diagnosis["verification_status"] != "unknown"
        result.summary = diagnosis["summary"] if established else ""
    evidence = detail.get("evidence", [])
    for item in evidence:
        result.evidence_sources[item["source_type"]] = (
            result.evidence_sources.get(item["source_type"], 0) + 1
        )
    repository_items = [e for e in evidence if e["source_type"] not in ("log", "kb", "incident")]
    if repository_items:
        result.repository_evidence_at_run_commit = all(
            e["commit_sha"] == result.head_sha for e in repository_items
        )
    proposals = detail.get("proposals", [])
    result.proposals = len(proposals)
    result.proposals_with_diff = sum(p["diff"] is not None for p in proposals)
    events = client.get(f"/api/investigations/{investigation_id}/events").json()
    result.timeline = [f"{e['node']}: {e['summary']}" for e in events]
    return result


def write_report(settings: Settings, runs: list[LiveRun], provider: str) -> None:
    REPORT.with_suffix(".jsonl").write_text(
        "".join(json.dumps(asdict(r)) + "\n" for r in runs), encoding="utf-8"
    )
    lines = [
        "# M4 live check: genuine failed GitHub Actions runs",
        "",
        "> Generated by `scripts/github_live_check.py`. Real public runs, read-only, through the "
        "real API, worker and agent graph. Raw rows in `eval/reports/m4-live-github.jsonl`.",
        "",
        f"- **Date (UTC):** {datetime.now(UTC):%Y-%m-%d %H:%M} · **Git:** {git_sha()}",
        f"- **Provider:** {provider} · **LLM:** {settings.llm_model} "
        f"(num_ctx {settings.llm_num_ctx}, num_gpu {settings.llm_num_gpu}) · **Embeddings:** "
        f"{settings.embedding_provider} ({settings.embedding_model})",
        "- **GitHub access:** read-only fine-grained token (job logs need sign-in); "
        "everything else is public data",
        f"- **GPU:** {gpu_description()} · **OS:** {platform.platform()}",
        "",
    ]
    for r in runs:
        lines += [
            f"## {r.repository} run {r.run_id} (#{r.run_number}, attempt {r.run_attempt})",
            "",
            f"- **Run:** {r.url}",
            f"- **Workflow / job:** {r.workflow} / {r.job_name}; failed step(s): "
            f"{', '.join(r.failed_steps) or 'none reported'}",
            f"- **Commit:** `{r.head_sha}`",
            f"- **Import:** {r.import_seconds} s; log {r.log_source}, {r.log_lines} lines "
            f"stored ({r.log_dropped_lines} earlier lines dropped to fit 2 MB); files read at the "
            f"commit: {', '.join(r.files_fetched) or 'none'}; unavailable: "
            f"{', '.join(r.files_missing) or 'none'}",
            f"- **Outcome:** status `{r.status}`; diagnosis `{r.category}` "
            f"(`{r.verification}`, rule hint `{r.rule_category}`); "
            f"{r.diagnosis_attempts} diagnosis attempt(s); citations valid "
            f"{r.citations_valid}/{r.citations_total}",
            f"- **Summary:** {r.summary or '(cause not established)'}",
            f"- **Evidence:** {r.evidence_sources}; repository evidence at the run's commit: "
            f"{r.repository_evidence_at_run_commit}",
            f"- **Remediation:** {r.proposals} proposal(s), {r.proposals_with_diff} with a "
            "validated diff; left for the owner's decision",
            f"- **Time:** {r.total_seconds} s end to end; diagnosis call {r.llm_ms} ms",
            f"- **LLM placement while running:** {r.placement}",
        ]
        if r.error:
            lines.append(f"- **Error:** {r.error}")
        lines += ["", "Timeline:", ""] + [f"1. {t}" for t in r.timeline] + [""]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("urls", nargs="+")
    parser.add_argument("--provider", choices=["ollama", "mock"], default="ollama")
    args = parser.parse_args()
    base = Settings()
    if base.github_token is None:
        print("KENSA_GITHUB_TOKEN is not set: GitHub serves job logs only to signed-in requests.")
        return 2
    settings = base.model_copy(update={"worker_enabled": True, "worker_poll_seconds": 0.5})
    runs: list[LiveRun] = []
    with TestClient(create_app(settings)) as client:
        for url in args.urls:
            print(f"Investigating {url} ...", flush=True)
            run = investigate(client, settings, url, args.provider)
            print(
                f"  {run.status}: {run.category} ({run.verification}), "
                f"{run.citations_valid}/{run.citations_total} citations, "
                f"{run.total_seconds} s",
                flush=True,
            )
            runs.append(run)
    write_report(settings, runs, args.provider)
    print(f"Report: {REPORT}")
    return 0 if all(r.status in SETTLED and r.status != "failed" for r in runs) else 1


if __name__ == "__main__":
    sys.exit(main())
