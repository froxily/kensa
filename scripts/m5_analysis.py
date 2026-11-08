"""M5 analysis of the held-out (and dev) diagnosis runs, using the metric definitions fixed in
eval/reports/m5-protocol.md before the test split was run. Read-only.

Inputs: eval/reports/m5-diagnosis-{dev,test}.jsonl, and the kensa_eval database (which holds the
most recent run, the test split) for confidence values and an independent citation re-check.
Writes eval/reports/m5-evaluation.md.

    uv run --directory backend --no-sync python ../scripts/m5_analysis.py
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from kensa.core.config import Settings
from kensa.db.models import Chunk, Citation, Diagnosis, Document, Evidence, Investigation
from kensa.db.session import build_engine
from kensa.ingestion.normalize import strip_timestamp

REPORTS = Path(__file__).resolve().parents[1] / "eval" / "reports"
ESTABLISHED = {"verified", "supported"}
# Dev fallback for "grounded but wrong" (the database holds only the test run): these statuses
# require an accepted citation from the log. The test split is checked directly in the database.
GROUNDED = {"verified", "supported", "contradicted"}
CONFIGS = [
    "rules-only (M3 agent)",
    "llm, no retrieval (log tail)",
    "llm + fts",
    "llm + hybrid (M2)",
    "agent + fts (M3)",
    "agent + hybrid (M3)",
]


def load(split: str) -> list[dict[str, Any]]:
    path = REPORTS / f"m5-diagnosis-{split}.jsonl"
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q / 100 * (len(ordered) - 1)))]


def summary_table(rows: list[dict[str, Any]]) -> list[str]:
    out = [
        "| config | correct | incorrect | abstained: correctly / missed | insufficient "
        "detected | false confidence | grounded but wrong (of which verified) | citations "
        "valid (final; all attempts) | wall p50 / p95 s | model call p50 / p95 s |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for config in CONFIGS:
        sel = [r for r in rows if r["config"] == config]
        if not sel:
            continue
        wrong = [r for r in sel if not r["correct"] and r["predicted"] not in (None, "unknown")]
        abstained = [r for r in sel if r["predicted"] == "unknown"]
        correct_abstain = [r for r in abstained if r["expected"] == "unknown"]
        insufficient = [r for r in sel if r["kind"] == "insufficient"]
        false_conf = [r for r in wrong if r["verification"] in ESTABLISHED]
        grounded = [
            r
            for r in wrong
            if (r["log_citations"] > 0 if "log_citations" in r else r["verification"] in GROUNDED)
        ]
        verified_wrong = [r for r in wrong if r["verification"] == "verified"]
        wall = [r["wall_ms"] / 1000 for r in sel if r.get("wall_ms")]
        llm = [r["llm_ms"] / 1000 for r in sel if r.get("llm_ms")]
        cv, ct = sum(r["citations_valid"] for r in sel), sum(r["citations_total"] for r in sel)
        av = sum(r.get("attempt_citations_valid", r["citations_valid"]) for r in sel)
        at = sum(r.get("attempt_citations_total", r["citations_total"]) for r in sel)
        share = f"{cv}/{ct} ({cv / ct:.0%})" if ct else "—"
        out.append(
            f"| {config} | {sum(r['correct'] for r in sel)}/{len(sel)} | {len(wrong)} "
            f"| {len(correct_abstain)} / {len(abstained) - len(correct_abstain)} "
            f"| {sum(r['correct'] for r in insufficient)}/{len(insufficient)} | {len(false_conf)} "
            f"| {len(grounded)} ({len(verified_wrong)}) | {share}; {av}/{at} "
            f"| {pct(wall, 50):.1f} / {pct(wall, 95):.1f} "
            f"| {pct(llm, 50):.1f} / {pct(llm, 95):.1f} |"
            if llm
            else f"| {config} | {sum(r['correct'] for r in sel)}/{len(sel)} | {len(wrong)} "
            f"| {len(correct_abstain)} / {len(abstained) - len(correct_abstain)} "
            f"| {sum(r['correct'] for r in insufficient)}/{len(insufficient)} | {len(false_conf)} "
            f"| {len(grounded)} ({len(verified_wrong)}) | {share}; {av}/{at} "
            f"| {pct(wall, 50):.1f} / {pct(wall, 95):.1f} | — |"
        )
    return out


def kind_table(rows: list[dict[str, Any]]) -> list[str]:
    out = ["| config | standard | misleading | insufficient |", "|---|---|---|---|"]
    for config in CONFIGS:
        sel = [r for r in rows if r["config"] == config]
        if not sel:
            continue
        cells = []
        for kind in ("standard", "misleading", "insufficient"):
            sub = [r for r in sel if r["kind"] == kind]
            cells.append(f"{sum(r['correct'] for r in sub)}/{len(sub)}" if sub else "—")
        out.append(f"| {config} | " + " | ".join(cells) + " |")
    return out


def norm(text: str, markdown: bool) -> str:
    text = strip_timestamp(text)
    if markdown:
        text = re.sub(r"[`*]", "", text)
    text = re.sub(r"^\s*L\d+:\s*", "", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def database_checks(test_rows: list[dict[str, Any]]) -> tuple[list[str], dict[int, float]]:
    """Confidence of each test run, its accepted citations from the run's own log (stored on the
    row as ``log_citations``), and an independent re-check of accepted citations. The
    kensa_eval database holds the test run; investigations are matched to rows by creation
    order (the harness creates them case by case, configuration by configuration)."""
    url = make_url(Settings().database_url.get_secret_value()).set(database="kensa_eval")
    database_url = SecretStr(url.render_as_string(hide_password=False))
    engine = build_engine(Settings(database_url=database_url))
    confidences: dict[int, float] = {}
    accepted = failures = 0
    with Session(engine) as session:
        investigations = session.scalars(
            select(Investigation).order_by(Investigation.created_at)
        ).all()
        if len(investigations) != len(test_rows):
            return [f"(database holds {len(investigations)} runs, expected {len(test_rows)})"], {}
        for index, investigation in enumerate(investigations):
            diagnosis = session.scalars(
                select(Diagnosis).where(Diagnosis.investigation_id == investigation.id)
            ).one()
            confidences[index] = diagnosis.confidence
            test_rows[index]["log_citations"] = 0
            for citation in session.scalars(
                select(Citation).where(Citation.diagnosis_id == diagnosis.id, Citation.valid)
            ):
                accepted += 1
                row = session.execute(
                    select(Chunk, Document.source_type)
                    .join(Evidence, Evidence.chunk_id == Chunk.id)
                    .join(Document, Document.id == Chunk.document_id)
                    .where(
                        Evidence.investigation_id == investigation.id,
                        Evidence.label == citation.evidence_label,
                    )
                ).first()
                ok = False
                if row is not None:
                    chunk, source_type = row
                    lines = chunk.content.split("\n")
                    position = citation.line_number - chunk.start_line
                    md = source_type in ("kb", "doc", "incident")
                    test_rows[index]["log_citations"] += source_type == "log"
                    if 0 <= position < len(lines):
                        ok = norm(citation.quote, md) in norm(lines[position], md)
                failures += not ok
    return [
        f"Independent re-check of every accepted citation in the test run: {accepted} accepted, "
        f"{failures} not found on their cited line."
    ], confidences


def main() -> int:
    dev, test = load("dev"), load("test")
    notes, confidences = database_checks(test)
    lines = ["# M5 evaluation: held-out test split (and dev under the same frozen system)", ""]
    lines += [
        "Metric definitions: `eval/reports/m5-protocol.md` (fixed before the test run). "
        'Raw rows: `m5-diagnosis-test.jsonl`, `m5-diagnosis-dev.jsonl`. "Grounded but wrong" is '
        "checked in the database for the test split (an accepted citation from the run's own log); "
        "for dev, whose runs are no longer stored, it is inferred from the status (verified, "
        "supported and contradicted all require an accepted log citation).",
        "",
        "## Held-out test split (20 cases, first and only run)",
        "",
        *summary_table(test),
        "",
        *kind_table(test),
        "",
        "## Dev split, same frozen system",
        "",
        *summary_table(dev),
        "",
        *kind_table(dev),
        "",
        "## Checks on the test run",
        "",
        *[f"- {n}" for n in notes],
    ]
    high_conf = [
        (i, r)
        for i, r in enumerate(test)
        if not r["correct"]
        and r["predicted"] not in (None, "unknown")
        and confidences.get(i, 0) >= 0.5
    ]
    lines.append(f"- Incorrect diagnoses with confidence ≥ 0.5 (test): {len(high_conf)}")
    lines += ["", "## Test cases answered incorrectly or missed, per configuration", ""]
    lines += ["| case | kind | expected | config | predicted | status | confidence |"]
    lines += ["|---|---|---|---|---|---|---|"]
    for index, r in enumerate(test):
        if not r["correct"]:
            confidence = confidences.get(index)
            shown = f"{confidence:.2f}" if confidence is not None else "—"
            lines.append(
                f"| {r['case']} | {r['kind']} | {r['expected']} | {r['config']} "
                f"| {r['predicted']} | {r['verification']} | {shown} |"
            )
    out = REPORTS / "m5-evaluation.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
