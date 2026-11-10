"""Evaluate v1.1 on the v3 sets (deterministic parts; no model).

    cd backend
    uv run --no-sync python ../scripts/evaluate_v3.py --dataset v3-change --split dev
    uv run --no-sync python ../scripts/evaluate_v3.py --dataset v3-history --split dev

* **v3-change:** each case's facts go through ``FixtureChangeSource`` and Kensa's analyser.
  Measured:
  - comparability accuracy (spec conformance), and the exact match of unverified factors
  - culprit Hit@1, Hit@3 and MRR on cases with a labelled culprit, against two naive baselines
    fixed in advance: "most recently changed file" and "largest diff"
  - suspects on cases with no culprit
* **v3-history:** every log is investigated in order (rules only, which is where fingerprints
  come from) in a dedicated ``kensa_eval_v3`` database. Measured:
  - pairwise precision and recall of "same primary fingerprint" against "same cluster"
  - similar-failure Recall@5 for recurrences
  - look-alikes merged with the failure they resemble

The held-out split needs ``--allow-test-split`` and is run once under the committed protocol
(``eval/reports/v11-protocol.md``). A split must be frozen first, except a dev split run with
``--draft`` while it is being written, which is labelled as such.
"""

import argparse
import itertools
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e2e_server import prepare_database
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from kensa.analysis.fingerprint import FINGERPRINT_VERSION
from kensa.changes.analyzer import RUNNER_IMAGE, analyze
from kensa.changes.service import failure_subjects
from kensa.changes.sources import FixtureChangeSource
from kensa.core.config import Settings
from kensa.db.models import (
    DEFAULT_WORKSPACE_ID,
    FailureFingerprint,
    Investigation,
    InvestigationFingerprint,
)
from kensa.db.session import build_engine
from kensa.evaluation.dataset import DatasetError
from kensa.evaluation.v3 import (
    load_change_cases,
    load_history_sequences,
    verify_v3,
)
from kensa.history.fingerprints import similar_failures
from kensa.investigations.service import NewInvestigation, create_investigation

REPO_ROOT = Path(__file__).resolve().parents[1]
DATASETS = REPO_ROOT / "eval" / "datasets"
REPORTS = REPO_ROOT / "eval" / "reports"
EVAL_DB = "kensa_eval_v3"
LLM_DB = "kensa_eval_v3_llm"
# The ablation (protocol v11): the production agent with hybrid retrieval, with and without the
# change analysis (its notes for the model and its diff documents as citable evidence).
LLM_CONFIGS = {"agent + hybrid, with changes": True, "agent + hybrid, without changes": False}
STRONGEST = "corroborated"


def git_sha() -> str:
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()


def _rank(paths: list[str], wanted: tuple[str, ...]) -> int | None:
    for index, path in enumerate(paths, 1):
        if path in wanted:
            return index
    return None


def _naive_rankings(folder: Path, failed_sha: str, baseline_sha: str) -> dict[str, list[str]]:
    """The two baselines fixed in the protocol, from the case's own comparison."""
    history = json.loads((folder / "history.json").read_text(encoding="utf-8-sig"))
    comparison = (history.get("comparisons") or {}).get(f"{baseline_sha}...{failed_sha}") or {}
    last_touched: dict[str, int] = {}
    size: dict[str, int] = {}
    for order, commit in enumerate(comparison.get("commits") or []):
        for change in commit.get("files") or []:
            path = change.get("path")
            last_touched[path] = order
            size[path] = (
                size.get(path, 0)
                + int(change.get("additions") or 0)
                + int(change.get("deletions") or 0)
            )
    return {
        "most_recent": sorted(last_touched, key=lambda p: (-last_touched[p], p)),
        "largest_diff": sorted(size, key=lambda p: (-size[p], p)),
    }


def evaluate_change(split: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    root = DATASETS / "v3-change"
    rows: list[dict[str, Any]] = []
    for case in load_change_cases(root, split):
        source = FixtureChangeSource(case.folder)
        failed, job = source.failed()
        lines = (case.folder / "failed.log").read_text(encoding="utf-8-sig").split("\n")
        subjects, category = failure_subjects(lines)
        result = analyze(failed, job, lines, source, subjects=subjects, category=category)
        suspects = [s.path for s in result.suspects]
        row: dict[str, Any] = {
            "id": case.id,
            "label_comparability": case.comparability,
            "comparability": result.comparability,
            "comparability_correct": result.comparability == case.comparability,
            "label_unverified": sorted(case.unverified),
            "unverified": sorted(result.unverified),
            "suspects": [
                {"path": s.path, "score": s.score, "status": s.status} for s in result.suspects
            ],
            "statuses_valid": all(s.status in ("correlated", "weak") for s in result.suspects),
            "culprits": list(case.culprit_paths),
        }
        if case.culprit_paths:
            wanted = tuple(RUNNER_IMAGE if p == "<runner-image>" else p for p in case.culprit_paths)
            row["rank"] = _rank(suspects, wanted)
            if result.baseline is not None:
                orders = _naive_rankings(case.folder, failed.head_sha, result.baseline.head_sha)
                row["naive_ranks"] = {k: _rank(v, wanted) for k, v in orders.items()}
            else:
                row["naive_ranks"] = {"most_recent": None, "largest_diff": None}
        else:
            row["correlated_without_culprit"] = sum(
                1 for s in result.suspects if s.status == "correlated"
            )
        rows.append(row)

    def hits(ranks: list[int | None], k: int) -> float:
        return sum(1 for r in ranks if r is not None and r <= k) / len(ranks) if ranks else 0.0

    def mrr(ranks: list[int | None]) -> float:
        return sum(1 / r for r in ranks if r) / len(ranks) if ranks else 0.0

    culprit_rows = [r for r in rows if r["culprits"]]
    ranks = [r["rank"] for r in culprit_rows]
    naive = {
        name: [r["naive_ranks"][name] for r in culprit_rows]
        for name in ("most_recent", "largest_diff")
    }
    no_culprit = [r for r in rows if not r["culprits"]]
    metrics = {
        "cases": len(rows),
        "comparability_accuracy": sum(r["comparability_correct"] for r in rows) / len(rows)
        if rows
        else 0.0,
        "unverified_exact": sum(r["unverified"] == r["label_unverified"] for r in rows) / len(rows)
        if rows
        else 0.0,
        "culprit_cases": len(culprit_rows),
        "hit_at_1": hits(ranks, 1),
        "hit_at_3": hits(ranks, 3),
        "mrr": mrr(ranks),
        "naive": {
            name: {"hit_at_1": hits(ranked, 1), "hit_at_3": hits(ranked, 3), "mrr": mrr(ranked)}
            for name, ranked in naive.items()
        },
        "no_culprit_cases": len(no_culprit),
        "no_culprit_with_correlated_suspect": sum(
            1 for r in no_culprit if r["correlated_without_culprit"]
        ),
        "statuses_valid": all(r["statuses_valid"] for r in rows),
    }
    return rows, metrics


def _eval_engine() -> Any:
    base = Settings(inference_provider="mock", embedding_provider="mock", worker_enabled=False)
    url = prepare_database(base, EVAL_DB)
    engine = build_engine(
        Settings(
            database_url=url,
            inference_provider="mock",
            embedding_provider="mock",
            worker_enabled=False,
        )
    )
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE failure_fingerprints, investigations RESTART IDENTITY CASCADE"))
    return engine


def evaluate_history(
    split: str, dataset: str = "v3-history"
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Pairwise metrics count only *exact* primary fingerprints as recurrence claims (D-057):
    an approximate fingerprint never claims that two failures are the same."""
    root = DATASETS / dataset
    sequences = load_history_sequences(root, split)
    engine = _eval_engine()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    ids: dict[str, Any] = {}
    meta: dict[str, dict[str, str]] = {}
    order = 0
    for sequence in sequences:
        for entry in sequence.entries:
            key = f"{sequence.id}/{entry.id}"
            with Session(engine) as session, session.begin():
                new = NewInvestigation(
                    title=key,
                    source="upload",
                    provider="mock",
                    document_name=entry.file,
                    log_text=entry.path.read_text(encoding="utf-8-sig"),
                )
                investigation = create_investigation(session, DEFAULT_WORKSPACE_ID, new, None)
                session.execute(
                    update(Investigation)
                    .where(Investigation.id == investigation.id)
                    .values(created_at=start + timedelta(minutes=order))
                )
                ids[key] = investigation.id
            meta[key] = {"cluster": entry.cluster, "relation": entry.relation}
            order += 1
    keys = list(ids)
    by_id = {v: k for k, v in ids.items()}
    with Session(engine) as session:
        primary = {
            by_id[iid]: fp
            for iid, fp in session.execute(
                select(InvestigationFingerprint.investigation_id, FailureFingerprint.hash)
                .join(
                    FailureFingerprint,
                    FailureFingerprint.id == InvestigationFingerprint.fingerprint_id,
                )
                .where(
                    InvestigationFingerprint.role == "primary",
                    FailureFingerprint.version == FINGERPRINT_VERSION,
                    FailureFingerprint.kind == "exact",
                )
            ).all()
        }
        rows: list[dict[str, Any]] = []
        for key in keys:
            found = similar_failures(
                session, DEFAULT_WORKSPACE_ID, ids[key], limit=5, earlier_only=True
            )
            earlier_same = [
                k for k in keys[: keys.index(key)] if meta[k]["cluster"] == meta[key]["cluster"]
            ]
            top = [by_id.get(s.investigation_id) for s in found]
            rows.append(
                {
                    "entry": key,
                    **meta[key],
                    "fingerprint": primary.get(key),
                    "has_earlier_same_cluster": bool(earlier_same),
                    "recall_at_5": any(k in earlier_same for k in top) if earlier_same else None,
                    "similar": [
                        {"entry": by_id.get(s.investigation_id), "match": s.match, "score": s.score}
                        for s in found
                    ],
                }
            )
    tp = fp = fn = 0
    for a, b in itertools.combinations(keys, 2):
        same_cluster = meta[a]["cluster"] == meta[b]["cluster"]
        same_print = primary.get(a) is not None and primary.get(a) == primary.get(b)
        tp += same_cluster and same_print
        fp += same_print and not same_cluster
        fn += same_cluster and not same_print
    recurrences = [r for r in rows if r["has_earlier_same_cluster"]]
    lookalikes = [r for r in rows if r["relation"] == "lookalike"]
    merged_lookalikes = 0
    for row in lookalikes:
        earlier = keys[: keys.index(row["entry"])]
        if any(
            primary.get(k) is not None
            and primary.get(k) == row["fingerprint"]
            and meta[k]["cluster"] != row["cluster"]
            for k in earlier
        ):
            merged_lookalikes += 1
    metrics = {
        "entries": len(rows),
        "sequences": len(sequences),
        "without_exact_fingerprint": sum(1 for r in rows if r["fingerprint"] is None),
        "fingerprint_version": FINGERPRINT_VERSION,
        "same_failure_labels": sum(
            1 for r in rows for s in r["similar"] if s["match"] == "same_failure"
        ),
        "same_failure_labels_wrong": sum(
            1
            for r in rows
            for s in r["similar"]
            if s["match"] == "same_failure"
            and meta.get(s["entry"] or "", {}).get("cluster") != r["cluster"]
        ),
        "pairwise_precision": tp / (tp + fp) if tp + fp else None,
        "pairwise_recall": tp / (tp + fn) if tp + fn else None,
        "same_cluster_pairs": tp + fn,
        "recurrences": len(recurrences),
        "recall_at_5": sum(1 for r in recurrences if r["recall_at_5"]) / len(recurrences)
        if recurrences
        else None,
        "lookalikes": len(lookalikes),
        "lookalikes_merged": merged_lookalikes,
    }
    return rows, metrics


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def evaluate_change_llm(split: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Category accuracy, wrong corroborated answers and diff-citation validity of the
    production agent, with and without the change analysis, on the same cases."""
    import time

    from evaluate import setup as eval_setup

    from kensa.agents.graph import AgentConfig, run_agent
    from kensa.changes.store import save_analysis
    from kensa.db.models import Chunk, Citation, Diagnosis, Document
    from kensa.indexing.service import embed_pending, ensure_repository, index_directory
    from kensa.inference.factory import provider_for
    from kensa.jobs import queue

    engine, settings, embedder, _meta = eval_setup("ollama", LLM_DB)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE failure_fingerprints, investigations RESTART IDENTITY CASCADE"))
    channels = frozenset({"signature", "fts", "vector"})
    provider = provider_for("ollama", settings)
    rows: list[dict[str, Any]] = []
    for case in load_change_cases(DATASETS / "v3-change", split):
        with Session(engine) as session, session.begin():
            repository = ensure_repository(session, DEFAULT_WORKSPACE_ID, f"eval-v3/{case.id}")
            indexed = index_directory(
                session, DEFAULT_WORKSPACE_ID, repository.id, case.folder / "repo"
            )
            if embedder is not None:
                embed_pending(session, embedder, DEFAULT_WORKSPACE_ID, indexed.document_ids)
            repository_id = repository.id
        source = FixtureChangeSource(case.folder)
        failed, job = source.failed()
        log_text = (case.folder / "failed.log").read_text(encoding="utf-8-sig")
        lines = log_text.split("\n")
        subjects, category = failure_subjects(lines)
        analysis = analyze(failed, job, lines, source, subjects=subjects, category=category)
        for config, with_changes in LLM_CONFIGS.items():
            with Session(engine) as session, session.begin():
                new = NewInvestigation(None, "upload", "ollama", "job.log", log_text, repository_id)
                investigation = create_investigation(session, DEFAULT_WORKSPACE_ID, new, None)
                investigation_id = investigation.id
                if with_changes:
                    save_analysis(
                        session,
                        DEFAULT_WORKSPACE_ID,
                        investigation_id,
                        failed.head_sha,
                        analysis,
                        diff_evidence=True,
                    )
            with Session(engine) as session, session.begin():
                lease = queue.claim(session, "eval", settings.worker_lease_seconds * 20)
            if lease is None or lease.investigation_id != investigation_id:
                raise RuntimeError(f"unexpected job state for {case.id}")
            started = time.perf_counter()
            final = run_agent(
                lease,
                engine,
                provider,
                database_url=settings.database_url.get_secret_value(),
                config=AgentConfig.from_settings(settings, channels),
                embedder=embedder,
            )
            wall_ms = int((time.perf_counter() - started) * 1000)
            state: dict[str, Any] = dict(final or {})
            with Session(engine) as session, session.begin():
                queue.complete(session, lease)
            with Session(engine) as session:
                diagnosis = session.scalars(
                    select(Diagnosis).where(Diagnosis.investigation_id == investigation_id)
                ).one()
                cited = session.execute(
                    select(Citation.valid, Document.source_type)
                    .outerjoin(Chunk, Chunk.id == Citation.chunk_id)
                    .outerjoin(Document, Document.id == Chunk.document_id)
                    .where(Citation.diagnosis_id == diagnosis.id)
                ).all()
            valid_types = {kind for valid, kind in cited if valid}
            correct = diagnosis.category == case.category
            row = {
                "id": case.id,
                "config": config,
                "comparability": analysis.comparability,
                "label_category": case.category,
                "category": diagnosis.category,
                "correct": correct,
                "status": diagnosis.verification_status,
                "wrong_corroborated": not correct and diagnosis.verification_status == STRONGEST,
                "citations_valid": sum(1 for valid, _ in cited if valid),
                "citations": len(cited),
                "diff_citations_valid": sum(1 for valid, kind in cited if valid and kind == "diff"),
                "diff_citations": sum(1 for _, kind in cited if kind == "diff"),
                "corroborated_on_diff_only": diagnosis.verification_status == STRONGEST
                and valid_types == {"diff"},
                "wall_ms": wall_ms,
                "llm_calls": int(state.get("llm_calls") or 0),
            }
            rows.append(row)
            print(f"  {case.id} / {config}: {row['category']} ({row['status']})", flush=True)
    engine.dispose()
    metrics: dict[str, Any] = {}
    for config in LLM_CONFIGS:
        sel = [r for r in rows if r["config"] == config]
        k = sum(r["correct"] for r in sel)
        lo, hi = wilson(k, len(sel))
        walls = sorted(r["wall_ms"] for r in sel)
        metrics[config] = {
            "cases": len(sel),
            "correct": k,
            "accuracy": k / len(sel) if sel else 0.0,
            "accuracy_wilson_95": [round(lo, 3), round(hi, 3)],
            "wrong_corroborated": sum(r["wrong_corroborated"] for r in sel),
            "corroborated": sum(r["status"] == STRONGEST for r in sel),
            "citations_valid": f"{sum(r['citations_valid'] for r in sel)}/"
            f"{sum(r['citations'] for r in sel)}",
            "diff_citations_valid": f"{sum(r['diff_citations_valid'] for r in sel)}/"
            f"{sum(r['diff_citations'] for r in sel)}",
            "corroborated_on_diff_only": sum(r["corroborated_on_diff_only"] for r in sel),
            "wall_p50_ms": walls[len(walls) // 2] if walls else None,
            "wall_p95_ms": walls[min(len(walls) - 1, int(len(walls) * 0.95))] if walls else None,
        }
    return rows, metrics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dataset", choices=["v3-change", "v3-history", "v4-history"], required=True
    )
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    parser.add_argument("--allow-test-split", action="store_true")
    parser.add_argument("--draft", action="store_true", help="dev only: an unfrozen dev split")
    parser.add_argument("--report-name")
    parser.add_argument(
        "--llm",
        action="store_true",
        help="v3-change only: the agent ablation with and without change evidence (Ollama)",
    )
    args = parser.parse_args()
    if args.llm and args.dataset != "v3-change":
        print("--llm is for v3-change only.")
        return 2
    if args.split == "test" and not args.allow_test_split:
        print("The held-out split runs once, under the protocol: pass --allow-test-split.")
        return 2
    if args.draft and args.split != "dev":
        print("--draft is for the dev split only.")
        return 2
    root = DATASETS / args.dataset
    try:
        digest = "DRAFT (not frozen)" if args.draft else verify_v3(root, args.split)
    except DatasetError as exc:
        print(exc)
        return 1
    if args.llm:
        rows, metrics = evaluate_change_llm(args.split)
    elif args.dataset == "v3-change":
        rows, metrics = evaluate_change(args.split)
    else:
        rows, metrics = evaluate_history(args.split, args.dataset)
    kind = "change-llm" if args.llm else args.dataset.removeprefix("v3-")
    name = args.report_name or f"v11-{kind}-{args.split}"
    if args.draft:
        name += "-draft"
    REPORTS.mkdir(parents=True, exist_ok=True)
    with (REPORTS / f"{name}.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, default=str, sort_keys=True) + "\n")
    lines = [
        f"# {args.dataset} evaluation: {args.split} split" + (" (DRAFT)" if args.draft else ""),
        "",
        f"> Generated by `scripts/evaluate_v3.py` on {args.dataset} (written by a separate LLM "
        "author, isolated from Kensa's code; see its AUTHORING files). "
        + (
            "Local model through the production agent (see the settings in `.env`). "
            if args.llm
            else "Deterministic: no model. "
        )
        + f"Raw rows: `eval/reports/{name}.jsonl`.",
        "",
        f"- **Date (UTC):** {datetime.now(UTC):%Y-%m-%d %H:%M} · **Git:** {git_sha()} · "
        f"**Dataset:** {digest}",
        "",
        "```json",
        json.dumps(metrics, indent=2, sort_keys=True),
        "```",
        "",
    ]
    (REPORTS / f"{name}.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(json.dumps(metrics, indent=2, sort_keys=True))
    print(f"Report: eval/reports/{name}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
