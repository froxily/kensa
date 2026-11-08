"""M5.1 analysis: compare systems on evaluation set v2 with the metrics fixed in
eval/reports/m51-protocol.md. Read-only; works on the harness's JSON-lines rows.

Statuses are compared across vocabularies: M5 used verified / supported / contradicted /
unknown, M5.1 uses corroborated / plausible / conflicting / not_established (D-040).

    uv run --directory backend --no-sync python ../scripts/m51_analysis.py \\
        --run "M5 (d7c6f56)=eval/reports/m51-v2-dev-m5.jsonl" \\
        --run "M5.1=eval/reports/m51-v2-dev.jsonl" --title "v2 dev" --out m51-v2-dev-comparison
"""

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
STRONGEST = {"verified", "corroborated"}
HEDGED = {"supported", "plausible"}
CONFLICT = {"contradicted", "conflicting"}
KINDS = ("standard", "masked", "misleading", "lookalike", "insufficient")


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q / 100 * (len(ordered) - 1)))]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def share(k: int, n: int) -> str:
    return f"{k}/{n} ({k / n:.0%})" if n else "—"


def summarise(label: str, rows: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for config in dict.fromkeys(r["config"] for r in rows):
        sel = [r for r in rows if r["config"] == config]
        n = len(sel)
        correct = sum(r["correct"] for r in sel)
        wrong = [r for r in sel if not r["correct"] and r["predicted"] not in (None, "unknown")]
        abstained = [r for r in sel if r["predicted"] == "unknown"]
        right_abstain = [r for r in abstained if r["expected"] == "unknown"]
        insufficient = [r for r in sel if r["kind"] == "insufficient"]
        strongest = [r for r in sel if r["verification"] in STRONGEST]
        lo, hi = wilson(correct, n)
        wall = [r["wall_ms"] / 1000 for r in sel if r.get("wall_ms")]
        llm = [r["llm_ms"] / 1000 for r in sel if r.get("llm_ms")]
        cv, ct = sum(r["citations_valid"] for r in sel), sum(r["citations_total"] for r in sel)
        out.append(
            f"| {label} | {config} | {correct}/{n} ({lo:.2f}-{hi:.2f}) | {len(wrong)} "
            f"| {sum(r['verification'] in STRONGEST for r in wrong)} "
            f"| {sum(r['verification'] in HEDGED for r in wrong)} "
            f"| {sum(r['verification'] in CONFLICT for r in wrong)} "
            f"| {len(right_abstain)} / {len(abstained) - len(right_abstain)} "
            f"| {sum(r['correct'] for r in insufficient)}/{len(insufficient)} "
            f"| {share(sum(r['correct'] for r in strongest), len(strongest))} "
            f"| {share(cv, ct)} "
            f"| {pct(wall, 50):.1f} / {pct(wall, 95):.1f} "
            + (f"| {pct(llm, 50):.1f} / {pct(llm, 95):.1f} |" if llm else "| — |")
        )
    return out


def kinds(label: str, rows: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for config in dict.fromkeys(r["config"] for r in rows):
        cells = []
        for kind in KINDS:
            sub = [r for r in rows if r["config"] == config and r["kind"] == kind]
            cells.append(f"{sum(r['correct'] for r in sub)}/{len(sub)}" if sub else "—")
        out.append(f"| {label} | {config} | " + " | ".join(cells) + " |")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare systems on evaluation set v2.")
    parser.add_argument("--run", action="append", required=True, help="label=path.jsonl")
    parser.add_argument("--title", required=True)
    parser.add_argument("--out", required=True, help="report stem under eval/reports/")
    args = parser.parse_args()
    runs: list[tuple[str, list[dict[str, Any]]]] = []
    for spec in args.run:
        label, path = spec.split("=", 1)
        file = REPO / path
        runs.append((label, [json.loads(x) for x in file.read_text("utf-8").splitlines() if x]))
    lines = [
        f"# M5.1 comparison: {args.title}",
        "",
        "Metric definitions: `eval/reports/m51-protocol.md`. Statuses are compared across "
        "vocabularies: the strongest status is `verified` (M5) or `corroborated` (M5.1); a hedged "
        "status is `supported` or `plausible`; a conflict status is `contradicted` or "
        "`conflicting`.",
        "",
        "| system | config | correct (95% CI) | incorrect | incorrect with the strongest "
        "status | incorrect, hedged | incorrect, flagged as conflicting | abstained correctly / "
        "missed | insufficient detected | strongest status correct | citations valid | wall p50 "
        "/ p95 s | model call p50 / p95 s |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for label, rows in runs:
        lines += summarise(label, rows)
    lines += ["", "## Accuracy by case kind", ""]
    lines += ["| system | config | " + " | ".join(KINDS) + " |", "|---|---|" + "---|" * len(KINDS)]
    for label, rows in runs:
        lines += kinds(label, rows)
    out = REPO / "eval" / "reports" / f"{args.out}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
