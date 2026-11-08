"""Summarise a local OpenTelemetry trace file (``.telemetry/**/traces.jsonl``): duration
percentiles per span name, and Ollama's own timing breakdown for model calls. Read-only.

    uv run --directory backend --no-sync python ../scripts/trace_summary.py <traces.jsonl> [...]
"""

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q / 100 * (len(ordered) - 1))))
    return ordered[index]


def main() -> int:
    spans = []
    for name in sys.argv[1:]:
        for line in Path(name).read_text(encoding="utf-8").splitlines():
            if line.strip():
                spans.append(json.loads(line))
    by_name: dict[str, list[float]] = defaultdict(list)
    for span in spans:
        by_name[span["name"]].append(float(span["duration_ms"]))
    print("| span | count | p50 ms | p95 ms | max ms |")
    print("|---|---|---|---|---|")
    for name in sorted(by_name, key=lambda n: -sum(by_name[n])):
        if name.startswith(("SELECT", "INSERT", "UPDATE", "DELETE", "connect")):
            continue
        values = by_name[name]
        print(
            f"| {name} | {len(values)} | {pct(values, 50):.0f} | {pct(values, 95):.0f} "
            f"| {max(values):.0f} |"
        )
    calls = [s["attributes"] for s in spans if s["name"] == "llm.generate"]
    by_task: dict[str, list[dict[str, float]]] = defaultdict(list)
    for attributes in calls:
        by_task[str(attributes.get("kensa.task"))].append(attributes)
    if calls:
        print(
            "\n| model call | n | total p50 ms | load p50 | prompt eval p50 | generation p50 "
            "| output tokens p50 | tokens/s p50 | calls with a model load > 1 s |"
        )
        print("|---|---|---|---|---|---|---|---|---|")
    for task, rows in by_task.items():

        def med(key: str, rows: list[dict[str, float]] = rows) -> float:
            return statistics.median(float(r.get(key) or 0) for r in rows)

        loads = sum(float(r.get("kensa.load_ms") or 0) > 1000 for r in rows)
        print(
            f"| {task} | {len(rows)} | {med('kensa.duration_ms'):.0f} | {med('kensa.load_ms'):.0f} "
            f"| {med('kensa.prompt_eval_ms'):.0f} | {med('kensa.eval_ms'):.0f} "
            f"| {med('kensa.output_tokens'):.0f} | {med('kensa.eval_tokens_per_s'):.1f} "
            f"| {loads}/{len(rows)} |"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
