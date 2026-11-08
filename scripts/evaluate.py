"""Evaluation: retrieval channels (Recall@k, MRR) and end-to-end diagnosis on a split.

Diagnosis configurations run either the linear M1/M2 pipeline or the M3 agent graph
(``--configs``; default: the M3 agent configurations).

Runs against a FROZEN dataset only (``--dataset v1|v2``; MANIFEST.sha256 must match) and in
its own database (``--database``, default ``kensa_eval``, emptied per run). Incident indexing is
off, so no case can retrieve another case's diagnosis. The held-out test split requires
``--allow-test-split``; tuning must only ever use the dev split. Never downloads models.

    uv run --directory backend --no-sync python ../scripts/evaluate.py retrieval --split dev
    uv run --directory backend --no-sync python ../scripts/evaluate.py diagnosis --split dev
    uv run --directory backend --no-sync python ../scripts/evaluate.py diagnosis --configs all
"""

import argparse
import json
import platform
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from benchmark_model import git_sha, gpu_description
from e2e_server import prepare_database
from pydantic import SecretStr
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from kensa.agents.graph import AgentConfig, run_agent
from kensa.agents.pipeline import InvestigationState, collect_evidence, run_investigation
from kensa.core.config import Settings
from kensa.core.telemetry import configure_tracing
from kensa.db.models import (
    DEFAULT_WORKSPACE_ID,
    Citation,
    Diagnosis,
    Investigation,
    RemediationProposal,
)
from kensa.db.session import build_engine
from kensa.evaluation.dataset import KINDS, Case, load_cases, verify_frozen
from kensa.evaluation.metrics import (
    RetrievedRef,
    hit_at_k,
    mean,
    percentile,
    recall_at_k,
    reciprocal_rank,
)
from kensa.indexing.service import (
    embed_pending,
    ensure_repository,
    index_directory,
    index_knowledge,
)
from kensa.inference.embeddings import Embedder
from kensa.inference.factory import embedder_for, provider_for
from kensa.inference.mock import MockProvider
from kensa.investigations.service import NewInvestigation, create_investigation
from kensa.jobs import queue
from kensa.retrieval.search import retrieve, vector_query_text

REPO_ROOT = Path(__file__).resolve().parents[1]
DATASETS = REPO_ROOT / "eval" / "datasets"
KNOWLEDGE = REPO_ROOT / "knowledge"
REPORTS = REPO_ROOT / "eval" / "reports"
RETRIEVAL_CONFIGS: dict[str, frozenset[str]] = {
    "signature": frozenset({"signature"}),
    "fts": frozenset({"fts"}),
    "vector": frozenset({"vector"}),
    "signature+fts (M1)": frozenset({"signature", "fts"}),
    "hybrid (M2)": frozenset({"signature", "fts", "vector"}),
}
ProviderName = Literal["ollama", "mock"]
Runner = Literal["pipeline", "agent"]
DIAGNOSIS_CONFIGS: dict[str, tuple[ProviderName, frozenset[str], Runner]] = {
    "rules-only": ("mock", frozenset({"signature", "fts"}), "pipeline"),
    "llm + signature+fts (M1)": ("ollama", frozenset({"signature", "fts"}), "pipeline"),
    "llm + hybrid (M2)": ("ollama", frozenset({"signature", "fts", "vector"}), "pipeline"),
    # M5 baseline: no retrieval at all. Every channel is off, so only the end of the log
    # (the last step chunks) reaches the model; no repository files or knowledge notes.
    "llm, no retrieval (log tail)": ("ollama", frozenset(), "pipeline"),
    "llm + fts": ("ollama", frozenset({"fts"}), "pipeline"),
    "rules-only (M3 agent)": ("mock", frozenset({"signature", "fts"}), "agent"),
    # Full-text search alone stays the retrieval baseline (D-027).
    "agent + fts (M3)": ("ollama", frozenset({"fts"}), "agent"),
    "agent + hybrid (M3)": ("ollama", frozenset({"signature", "fts", "vector"}), "agent"),
}
DEFAULT_DIAGNOSIS_CONFIGS = ("rules-only (M3 agent)", "agent + fts (M3)", "agent + hybrid (M3)")
# The M5 comparison (fixed before the held-out run): rules-only, an LLM without retrieval, the
# LLM pipeline with full text and with hybrid retrieval, and the agent with each.
M5_DIAGNOSIS_CONFIGS = (
    "rules-only (M3 agent)",
    "llm, no retrieval (log tail)",
    "llm + fts",
    "llm + hybrid (M2)",
    "agent + fts (M3)",
    "agent + hybrid (M3)",
)
# M5.1 (fixed before the v2 held-out run): rules-only, the fastest LLM pipeline, and the agent
# with each retrieval mode. Four configurations keep a 60-case run within the 4 GB laptop's time.
M51_DIAGNOSIS_CONFIGS = (
    "rules-only (M3 agent)",
    "llm + fts",
    "agent + fts (M3)",
    "agent + hybrid (M3)",
)
# The strongest root-cause status in either vocabulary (M5.1 renamed "verified").
STRONGEST = frozenset({"corroborated", "verified"})


def setup(
    embedder_name: str, database: str = "kensa_eval"
) -> tuple[Engine, Settings, Embedder | None, dict[str, Any]]:
    base = Settings()
    settings = base.model_copy(
        update={
            "database_url": SecretStr(prepare_database(base, database)),
            "embedding_provider": embedder_name,
            "index_incidents": False,
        }
    )
    engine = build_engine(settings)
    embedder = embedder_for(settings)
    started = time.perf_counter()
    with Session(engine) as session, session.begin():
        index_knowledge(session, DEFAULT_WORKSPACE_ID, KNOWLEDGE)
        kb_chunks = embed_pending(session, embedder, DEFAULT_WORKSPACE_ID) if embedder else 0
    meta = {"kb_chunks": kb_chunks, "kb_index_seconds": round(time.perf_counter() - started, 2)}
    return engine, settings, embedder, meta


def new_investigation(
    engine: Engine, case: Case, repository_id: uuid.UUID, provider: ProviderName
) -> uuid.UUID:
    with Session(engine) as session, session.begin():
        new = NewInvestigation(
            None,
            "upload",
            provider,
            "job.log",
            case.log_path.read_text(encoding="utf-8"),
            repository_id,
        )
        return create_investigation(session, DEFAULT_WORKSPACE_ID, new, None).id


def index_case(engine: Engine, case: Case, embedder: Embedder | None) -> tuple[uuid.UUID, float]:
    started = time.perf_counter()
    with Session(engine) as session, session.begin():
        repository = ensure_repository(session, DEFAULT_WORKSPACE_ID, f"eval/{case.id}")
        result = index_directory(session, DEFAULT_WORKSPACE_ID, repository.id, case.repo_path)
        if embedder is not None:
            embed_pending(session, embedder, DEFAULT_WORKSPACE_ID, result.document_ids)
        return repository.id, time.perf_counter() - started


def to_ref(source_type: str, name: str, start: int, end: int) -> RetrievedRef:
    return RetrievedRef("log" if source_type == "log" else name, start, end)


# ------------------------------------------------------------------------------- retrieval ---


@dataclass
class RetrievalRow:
    case: str
    kind: str
    category: str
    config: str
    recall_5: float
    recall_10: float
    mrr: float
    hit_5: bool
    retrieved: list[str]


def run_retrieval(
    cases: list[Case], embedder_name: str
) -> tuple[list[RetrievalRow], dict[str, Any]]:
    engine, _settings, embedder, meta = setup(embedder_name)
    rows: list[RetrievalRow] = []
    query_ms: list[float] = []
    for case in cases:
        repository_id, _ = index_case(engine, case, embedder)
        investigation_id = new_investigation(engine, case, repository_id, "mock")
        with Session(engine) as session, session.begin():
            investigation = session.get_one(Investigation, investigation_id)
            state = InvestigationState(investigation_id, DEFAULT_WORKSPACE_ID, investigation.title)
            collect_evidence(session, state)
            vector = None
            if embedder is not None:
                embed_pending(session, embedder, DEFAULT_WORKSPACE_ID)
                started = time.perf_counter()
                vector = embedder.embed_query(
                    vector_query_text(state.title, state.signatures, state.log_tail)
                )
                query_ms.append((time.perf_counter() - started) * 1000)
            for config, channels in RETRIEVAL_CONFIGS.items():
                if "vector" in channels and vector is None:
                    continue
                found = retrieve(
                    session,
                    workspace_id=DEFAULT_WORKSPACE_ID,
                    investigation_id=investigation_id,
                    signatures=state.signatures,
                    repository_id=repository_id,
                    query_vector=vector,
                    channels=channels,
                    max_chunks=10,
                )
                refs = [
                    to_ref(c.source_type, c.document_name, c.start_line, c.end_line) for c in found
                ]
                rows.append(
                    RetrievalRow(
                        case.id,
                        case.kind,
                        case.category,
                        config,
                        recall_at_k(refs, case.evidence, 5),
                        recall_at_k(refs, case.evidence, 10),
                        reciprocal_rank(refs, case.evidence),
                        hit_at_k(refs, case.evidence, 5),
                        [f"{r.path}:{r.start_line}-{r.end_line}" for r in refs],
                    )
                )
        print(f"  {case.id}: done", flush=True)
    engine.dispose()
    meta["query_embed_ms_p50"] = round(percentile(query_ms, 50), 1)
    return rows, meta


def retrieval_table(rows: list[RetrievalRow], subset: str | None = None) -> list[str]:
    lines = ["| config | cases | Recall@5 | Recall@10 | MRR | hit@5 |", "|---|---|---|---|---|---|"]
    for config in RETRIEVAL_CONFIGS:
        selected = [r for r in rows if r.config == config and (subset is None or r.kind == subset)]
        if not selected:
            continue
        lines.append(
            f"| {config} | {len(selected)} | {mean([r.recall_5 for r in selected]):.3f} "
            f"| {mean([r.recall_10 for r in selected]):.3f} "
            f"| {mean([r.mrr for r in selected]):.3f} "
            f"| {sum(r.hit_5 for r in selected)}/{len(selected)} |"
        )
    return lines


# ------------------------------------------------------------------------------- diagnosis ---


@dataclass
class DiagnosisRow:
    case: str
    kind: str
    expected: str
    config: str
    predicted: str | None
    correct: bool
    verification: str | None
    citations_valid: int
    citations_total: int
    fix_keyword_hit: bool | None
    llm_ms: int | None
    prompt_tokens: int | None
    runner: str = "pipeline"
    wall_ms: int | None = None
    diagnosis_attempts: int = 1
    llm_calls: int = 0
    # Citations of every attempt, including ones the verifier loop replaced.
    attempt_citations_valid: int = 0
    attempt_citations_total: int = 0
    evidence_complete: bool | None = None
    proposals: int = 0
    diffs: int = 0


def run_diagnosis(
    cases: list[Case], embedder_name: str, configs: list[str], database: str = "kensa_eval"
) -> tuple[list[DiagnosisRow], dict[str, Any]]:
    engine, settings, embedder, meta = setup(embedder_name, database)
    rows: list[DiagnosisRow] = []
    for case in cases:
        repository_id, _ = index_case(engine, case, embedder)
        for config in configs:
            provider_name, channels, runner = DIAGNOSIS_CONFIGS[config]
            investigation_id = new_investigation(engine, case, repository_id, provider_name)
            with Session(engine) as session, session.begin():
                lease = queue.claim(session, "eval", settings.worker_lease_seconds * 20)
            if lease is None or lease.investigation_id != investigation_id:
                raise RuntimeError(f"unexpected job state for {case.id}")
            provider = (
                MockProvider() if provider_name == "mock" else provider_for("ollama", settings)
            )
            started = time.perf_counter()
            state: dict[str, Any] = {}
            if runner == "agent":
                final = run_agent(
                    lease,
                    engine,
                    provider,
                    database_url=settings.database_url.get_secret_value(),
                    config=AgentConfig.from_settings(settings, channels),
                    embedder=embedder,
                )
                state = dict(final or {})
            else:
                run_investigation(
                    lease,
                    engine,
                    provider,
                    num_ctx=settings.llm_num_ctx,
                    embedder=embedder,
                    channels=channels,
                    index_incidents=False,
                )
            wall_ms = int((time.perf_counter() - started) * 1000)
            with Session(engine) as session, session.begin():
                queue.complete(session, lease)
            with Session(engine) as session:
                diagnosis = session.scalars(
                    select(Diagnosis).where(Diagnosis.investigation_id == investigation_id)
                ).one()
                citations = session.scalars(
                    select(Citation).where(Citation.diagnosis_id == diagnosis.id)
                ).all()
                proposals = session.scalars(
                    select(RemediationProposal).where(
                        RemediationProposal.investigation_id == investigation_id
                    )
                ).all()
            attempts = state.get("attempts") or [
                {"valid": sum(c.valid for c in citations), "total": len(citations)}
            ]
            pipeline_calls = 1 if provider_name == "ollama" else 0
            fixes = " ".join(diagnosis.recommended_fixes).lower()
            keywords = [k.lower() for k in case.fix_keywords]
            rows.append(
                DiagnosisRow(
                    case.id,
                    case.kind,
                    case.category,
                    config,
                    diagnosis.category,
                    diagnosis.category == case.category,
                    diagnosis.verification_status,
                    sum(c.valid for c in citations),
                    len(citations),
                    any(k in fixes for k in keywords) if keywords else None,
                    diagnosis.duration_ms,
                    diagnosis.prompt_tokens,
                    runner=runner,
                    wall_ms=wall_ms,
                    diagnosis_attempts=diagnosis.diagnosis_attempts,
                    llm_calls=int(state.get("llm_calls", pipeline_calls)),
                    attempt_citations_valid=sum(int(a["valid"]) for a in attempts),
                    attempt_citations_total=sum(int(a["total"]) for a in attempts),
                    evidence_complete=diagnosis.evidence_complete,
                    proposals=len(proposals),
                    diffs=sum(p.diff is not None for p in proposals),
                )
            )
            print(
                f"  {case.id} / {config}: {diagnosis.category} ({diagnosis.verification_status})",
                flush=True,
            )
    engine.dispose()
    return rows, meta


def agent_table(rows: list[DiagnosisRow]) -> list[str]:
    """What the M3 checks and loop did: abstention, wrong-but-confident answers, attempts."""
    lines = [
        "| config | wrong but not abstaining | abstained (log shows no failure) "
        "| attempts mean / max | model calls | citations valid, all attempts "
        "| proposals / with diff | wall p50 / p95 ms |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for config in DIAGNOSIS_CONFIGS:
        sel = [r for r in rows if r.config == config]
        if not sel:
            continue
        wrong = [r for r in sel if not r.correct and r.predicted not in (None, "unknown")]
        abstained = [r for r in sel if r.evidence_complete is False]
        attempts = [r.diagnosis_attempts for r in sel]
        wall = [float(r.wall_ms) for r in sel if r.wall_ms]
        lines.append(
            f"| {config} | {len(wrong)}/{len(sel)} | {len(abstained)} "
            f"| {mean([float(a) for a in attempts]):.2f} / {max(attempts)} "
            f"| {sum(r.llm_calls for r in sel)} "
            f"| {sum(r.attempt_citations_valid for r in sel)}/"
            f"{sum(r.attempt_citations_total for r in sel)} "
            f"| {sum(r.proposals for r in sel)} / {sum(r.diffs for r in sel)} "
            f"| {percentile(wall, 50):.0f} / {percentile(wall, 95):.0f} |"
        )
    return lines


def diagnosis_table(rows: list[DiagnosisRow]) -> list[str]:
    kinds = [k for k in KINDS if any(r.kind == k for r in rows)]
    lines = [
        "| config | runs | accuracy | "
        + " | ".join(kinds)
        + " | strongest status (corroborated / verified) | citations valid | fix keyword hit "
        "| LLM p50 / p95 ms |",
        "|---|---|---|" + "---|" * len(kinds) + "---|---|---|---|",
    ]
    for config in DIAGNOSIS_CONFIGS:
        sel = [r for r in rows if r.config == config]
        if not sel:
            continue

        def acc(kind: str, sel: list[DiagnosisRow] = sel) -> str:
            subset = [r for r in sel if r.kind == kind]
            return f"{sum(r.correct for r in subset)}/{len(subset)}" if subset else "—"

        total_cit = sum(r.citations_total for r in sel)
        fix = [r.fix_keyword_hit for r in sel if r.fix_keyword_hit is not None]
        ms = [float(r.llm_ms) for r in sel if r.llm_ms]
        lines.append(
            f"| {config} | {len(sel)} | {sum(r.correct for r in sel)}/{len(sel)} | "
            + " | ".join(acc(kind) for kind in kinds)
            + f" | {sum(r.verification in STRONGEST for r in sel)}/{len(sel)} "
            f"| {sum(r.citations_valid for r in sel)}/{total_cit} | {sum(fix)}/{len(fix)} "
            f"| {percentile(ms, 50):.0f} / {percentile(ms, 95):.0f} |"
        )
    return lines


# ------------------------------------------------------------------------------------ main ---


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("mode", choices=["retrieval", "diagnosis"])
    parser.add_argument("--dataset", choices=["v1", "v2"], default="v1")
    parser.add_argument("--database", default="kensa_eval", help="evaluation database name")
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--allow-test-split", action="store_true")
    parser.add_argument("--embedder", choices=["ollama", "mock"], default="ollama")
    parser.add_argument(
        "--configs",
        default=",".join(DEFAULT_DIAGNOSIS_CONFIGS),
        help='diagnosis configurations, comma-separated, "all", "m5" or "m51"',
    )
    parser.add_argument("--limit", type=int, default=None, help="dev split only: first N cases")
    parser.add_argument("--report-name", default=None, help="report file stem (no extension)")
    args = parser.parse_args()
    if args.configs == "all":
        configs = list(DIAGNOSIS_CONFIGS)
    elif args.configs == "m5":
        configs = list(M5_DIAGNOSIS_CONFIGS)
    elif args.configs == "m51":
        configs = list(M51_DIAGNOSIS_CONFIGS)
    else:
        configs = [c.strip() for c in args.configs.split(",") if c.strip()]
    unknown = [c for c in configs if c not in DIAGNOSIS_CONFIGS]
    if unknown:
        print(f"Unknown configurations: {unknown}. Choose from {list(DIAGNOSIS_CONFIGS)}.")
        return 2
    if args.split == "test" and not args.allow_test_split:
        print("Refusing to evaluate the held-out test split without --allow-test-split.")
        return 2
    if args.limit is not None and args.split == "test":
        print("The held-out test split always runs in full; --limit is for dev only.")
        return 2
    if not args.database.startswith("kensa_eval"):
        print("The evaluation database name must start with kensa_eval (it is emptied per run).")
        return 2
    dataset = DATASETS / args.dataset
    digest = verify_frozen(dataset, args.split)
    cases = load_cases(dataset, args.split)[: args.limit]
    print(
        f"{args.mode} on {args.dataset} {args.split}: {len(cases)} cases, dataset {digest}",
        flush=True,
    )
    run_name = args.report_name or f"{args.mode}-{args.split}-{datetime.now(UTC):%Y%m%d-%H%M%S}"
    tracing = configure_tracing(True, REPO_ROOT / ".telemetry" / run_name)
    print(f"Traces: .telemetry/{run_name}/traces.jsonl", flush=True)

    started = time.perf_counter()
    if args.mode == "retrieval":
        r_rows, meta = run_retrieval(cases, args.embedder)
        rows: list[Any] = r_rows
        tables = ["## All cases", "", *retrieval_table(r_rows)]
        for kind in KINDS:
            if any(r.kind == kind for r in r_rows):
                tables += ["", f"## {kind} cases", "", *retrieval_table(r_rows, kind)]
    else:
        d_rows, meta = run_diagnosis(cases, args.embedder, configs, args.database)
        rows = d_rows
        tables = ["## Results", "", *diagnosis_table(d_rows)]
        if any(r.runner == "agent" for r in d_rows):
            tables += ["", "## Agent workflow (M3)", "", *agent_table(d_rows)]
    elapsed = time.perf_counter() - started
    if tracing is not None:
        tracing.force_flush()

    REPORTS.mkdir(parents=True, exist_ok=True)
    milestone = (
        "m3"
        if args.mode == "diagnosis" and "agent" in {DIAGNOSIS_CONFIGS[c][2] for c in configs}
        else "m2"
    )
    stem = REPORTS / (args.report_name or f"{milestone}-{args.mode}-{args.split}-{args.embedder}")
    stem.with_suffix(".jsonl").write_text(
        "".join(json.dumps(asdict(r)) + "\n" for r in rows), encoding="utf-8"
    )
    settings = Settings()
    embedding_model = settings.embedding_model if args.embedder == "ollama" else "hashing-v1"
    header = [
        f"# {(args.report_name or milestone).upper()} {args.mode} evaluation: {args.split} split "
        f"({args.embedder} embeddings)",
        "",
        "> Generated by `scripts/evaluate.py` on the frozen dataset "
        f"(eval/datasets/{args.dataset}, "
        "written by a separate LLM author isolated from Kensa's code; see its AUTHORING files). "
        "Real measurements on this machine; "
        f"raw per-case rows in `{stem.with_suffix('.jsonl').relative_to(REPO_ROOT).as_posix()}`.",
        "",
        f"- **Date (UTC):** {datetime.now(UTC):%Y-%m-%d %H:%M} · **Git:** {git_sha()} "
        f"· **Dataset:** {digest}",
        f"- **Embeddings:** {args.embedder} ({embedding_model}, num_gpu "
        f"{settings.embedding_num_gpu}) · **LLM:** {settings.llm_model} "
        f"(num_ctx {settings.llm_num_ctx}, num_gpu {settings.llm_num_gpu})",
        f"- **GPU:** {gpu_description()} · **OS:** {platform.platform()}",
        f"- **Run time:** {elapsed:.0f} s · **Setup:** {json.dumps(meta)}",
        "",
    ]
    stem.with_suffix(".md").write_text("\n".join(header + tables) + "\n", encoding="utf-8")
    print("\n".join(tables))
    print(f"Report: {stem.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
