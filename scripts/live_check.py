"""M1 live check: real investigations through the real worker and the local Ollama model.

Runs the bundled sample incidents plus one long synthetic log (to fill the evidence budget)
with the ``ollama`` provider, samples VRAM throughout, and writes
``eval/reports/m1-live-check.md`` with raw JSONL. Uses the development database from ``.env``,
so the runs are visible in the UI afterwards. Never downloads models.

Exit status is non-zero only if an investigation did not complete; citation validity is a
reported result, not a failure condition (the verifier's job is to reject weak citations).

    uv run --directory backend --no-sync python ../scripts/live_check.py
"""

import json
import platform
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
from benchmark_model import (
    VramSampler,
    git_sha,
    gpu_description,
    ollama_ram_mib,
    unload,
    vram_used_mib,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from kensa.agents.handler import make_investigate_handler, on_job_outcome
from kensa.core.config import Settings
from kensa.db.models import DEFAULT_WORKSPACE_ID, Citation, Diagnosis, Investigation
from kensa.db.session import build_engine
from kensa.inference.ollama import normalize_model_name
from kensa.investigations.samples import SAMPLES
from kensa.investigations.service import INVESTIGATE_JOB, NewInvestigation, create_investigation
from kensa.jobs.worker import Worker

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "eval" / "reports" / "m1-live-check.md"


def long_log() -> str:
    """A synthetic pytest run with many failures: enough evidence to fill the prompt budget."""
    lines = ["##[group]Run uv run pytest -q", "uv run pytest -q", "##[endgroup]"]
    for n in range(60):
        lines += [
            f"tests/test_orders.py::test_case_{n} PASSED"
            if n % 3
            else f"_____ test_total_{n} _____",
            f"    def test_total_{n}(client):",
            f"        response = client.get('/orders/{n}/total')",
            f">       assert response.json()['total'] == {n * 10}",
            f"E       AssertionError: assert {n * 10 + 1} == {n * 10}",
            "",
        ]
    lines += [
        f"FAILED tests/test_orders.py::test_total_{n} - AssertionError" for n in range(0, 60, 3)
    ]
    lines += [
        "======= 20 failed, 40 passed in 9.81s =======",
        "##[error]Process completed with exit code 1.",
    ]
    return "\n".join(lines) + "\n"


@dataclass
class LiveResult:
    case: str
    status: str
    error_code: str | None
    rule_category: str | None
    category: str | None
    verification_status: str | None
    citations_valid: int
    citations_total: int
    confidence: float | None
    prompt_tokens: int | None
    output_tokens: int | None
    llm_duration_ms: int | None
    wall_s: float
    peak_vram_mib: int | None
    model_size_mib: int | None
    model_vram_mib: int | None
    ollama_ram_mib: int | None
    summary: str | None


def placement(settings: Settings) -> tuple[int | None, int | None]:
    try:
        with httpx.Client(base_url=settings.ollama_base_url, timeout=5) as client:
            models = client.get("/api/ps").json().get("models", [])
    except httpx.HTTPError:
        return None, None
    for entry in models:
        if normalize_model_name(str(entry.get("name"))) == normalize_model_name(settings.llm_model):
            return int(entry["size"]) // 2**20, int(entry["size_vram"]) // 2**20
    return None, None


def run_case(settings: Settings, worker: Worker, name: str, title: str, log: str) -> LiveResult:
    with Session(worker.engine) as session, session.begin():
        new = NewInvestigation(title, "sample", "ollama", f"{name}.log", log)
        investigation_id = create_investigation(
            session, DEFAULT_WORKSPACE_ID, new, settings.llm_model
        ).id
    started = time.perf_counter()
    with VramSampler() as sampler:
        while worker.run_once():
            pass
        size, in_vram = placement(settings)
        ram = ollama_ram_mib()
    wall = time.perf_counter() - started

    with Session(worker.engine) as session:
        investigation = session.get_one(Investigation, investigation_id)
        diagnosis = session.scalars(
            select(Diagnosis).where(Diagnosis.investigation_id == investigation_id)
        ).one_or_none()
        citations = (
            session.scalars(select(Citation).where(Citation.diagnosis_id == diagnosis.id)).all()
            if diagnosis
            else []
        )
        return LiveResult(
            case=name,
            status=investigation.status,
            error_code=investigation.error_code,
            rule_category=investigation.rule_category,
            category=diagnosis.category if diagnosis else None,
            verification_status=diagnosis.verification_status if diagnosis else None,
            citations_valid=sum(c.valid for c in citations),
            citations_total=len(citations),
            confidence=diagnosis.confidence if diagnosis else None,
            prompt_tokens=diagnosis.prompt_tokens if diagnosis else None,
            output_tokens=diagnosis.output_tokens if diagnosis else None,
            llm_duration_ms=diagnosis.duration_ms if diagnosis else None,
            wall_s=round(wall, 2),
            peak_vram_mib=sampler.peak_mib,
            model_size_mib=size,
            model_vram_mib=in_vram,
            ollama_ram_mib=ram,
            summary=diagnosis.summary if diagnosis else None,
        )


def write_report(settings: Settings, baseline: int | None, results: list[LiveResult]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    raw = OUT.with_suffix(".jsonl")
    raw.write_text("".join(json.dumps(asdict(r)) + "\n" for r in results), encoding="utf-8")
    rows = [
        f"| {r.case} | {r.status} | {r.rule_category} | {r.category} | {r.verification_status} "
        f"| {r.citations_valid}/{r.citations_total} | {r.confidence} | {r.prompt_tokens} "
        f"| {r.output_tokens} | {r.llm_duration_ms} | {r.peak_vram_mib} "
        f"| {r.model_vram_mib}/{r.model_size_mib} |"
        for r in results
    ]
    lines = [
        "# M1 live check (local Ollama)",
        "",
        "> Real investigations through the worker and the local model on this machine. Three "
        "inputs are the bundled synthetic samples and one is a long synthetic log built to fill "
        "the evidence budget. A functional and resource check, **not an accuracy evaluation**. "
        f"Raw data: `{raw.relative_to(REPO_ROOT).as_posix()}`.",
        "",
        f"- **Date (UTC):** {datetime.now(UTC):%Y-%m-%d %H:%M} · **Git:** {git_sha()}",
        f"- **Model:** {settings.llm_model} · num_ctx {settings.llm_num_ctx} · "
        f"num_gpu {settings.llm_num_gpu}",
        f"- **GPU:** {gpu_description()} · VRAM used before: {baseline} MiB",
        f"- **OS / Python:** {platform.platform()} / {platform.python_version()}",
        "",
        "| case | status | rule hint | model category | verification | valid citations "
        "| confidence | prompt tok | output tok | LLM ms | peak VRAM MiB "
        "| model in VRAM/size MiB |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
        *rows,
        "",
        "## Model summaries (verbatim)",
        "",
        *[f"- **{r.case}:** {r.summary}" for r in results],
    ]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    settings = Settings()
    engine = build_engine(settings)
    worker = Worker(
        engine,
        {INVESTIGATE_JOB: make_investigate_handler(settings)},
        owner="live-check",
        on_outcome=on_job_outcome,
    )
    with httpx.Client(base_url=settings.ollama_base_url, timeout=60) as client:
        unload(client, settings.llm_model)  # clean VRAM baseline; first case includes the load
    time.sleep(2)
    baseline = vram_used_mib()
    cases = [(s.id, f"[live check] {s.title}", s.read()) for s in SAMPLES]
    cases.append(("long-pytest-log", "[live check] Long pytest log", long_log()))
    results = []
    for name, title, log in cases:
        print(f"running {name} ...", flush=True)
        result = run_case(settings, worker, name, title, log)
        print(
            f"  -> {result.status} {result.category} {result.verification_status} "
            f"citations {result.citations_valid}/{result.citations_total} "
            f"peak VRAM {result.peak_vram_mib} MiB",
            flush=True,
        )
        results.append(result)
    write_report(settings, baseline, results)
    engine.dispose()
    print(f"Report written to {OUT}")
    return 0 if all(r.status == "completed" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
