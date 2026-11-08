"""Evidence completeness (M3): does the log show a failure at all, and does the retrieved
evidence contain the lines that show it?

Deterministic and cheap; runs before any model call. Three outcomes:
* ``no_failure_shown``: the log has no failure vocabulary anywhere (for example it stops before
  the failing step's output). Kensa abstains without asking the model, because no answer could
  be grounded in this run's log.
* ``missing_lines``: the log shows a failure, but the retrieved excerpts do not include its key
  lines. Targeted retrieval adds them (bounded rounds).
* ``sufficient``.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from kensa.agents.evidence import EvidenceItem
from kensa.analysis.classifier import RuleClassification
from kensa.analysis.indicators import FAILURE_MARKER, TRUNCATION_MARKER
from kensa.analysis.signatures import SignatureMatch
from kensa.ingestion.normalize import strip_timestamp

MAX_SCANNED_MARKERS = 200
KEY_LINES = 3

CompletenessStatus = Literal["sufficient", "missing_lines", "no_failure_shown"]


@dataclass(frozen=True)
class LogScan:
    failure_lines: tuple[int, ...]
    truncation_lines: tuple[int, ...]
    line_count: int


@dataclass(frozen=True)
class Completeness:
    status: CompletenessStatus
    key_lines: tuple[int, ...]
    missing_lines: tuple[int, ...]
    notes: tuple[str, ...]


def scan_log(lines: Sequence[str]) -> LogScan:
    failures: list[int] = []
    truncations: list[int] = []
    for number, raw in enumerate(lines, start=1):
        line = strip_timestamp(raw)
        if FAILURE_MARKER.search(line) and len(failures) < MAX_SCANNED_MARKERS:
            failures.append(number)
        if TRUNCATION_MARKER.search(line):
            truncations.append(number)
    return LogScan(tuple(failures), tuple(truncations), len(lines))


def assess(
    scan: LogScan,
    signatures: Sequence[SignatureMatch],
    rule: RuleClassification,
    evidence: Sequence[EvidenceItem],
) -> Completeness:
    notes: list[str] = []
    if scan.truncation_lines:
        notes.append(
            f"The log says it is truncated (L{scan.truncation_lines[0]}); the failing step's "
            "output may be incomplete."
        )
    if not scan.failure_lines and not signatures:
        notes.insert(
            0,
            f"The log ({scan.line_count} lines) shows no failure: no error line, failing exit "
            "status or failing test.",
        )
        return Completeness("no_failure_shown", (), (), tuple(notes))

    # The lines that show the failure: the rule's strongest signals, or else the last generic
    # failure markers (the decisive error usually sits just before the job's exit status).
    if rule.category != "unknown":
        key = rule.supporting_lines[:KEY_LINES]
    else:
        key = tuple(sorted({s.line_number for s in signatures} | set(scan.failure_lines)))[
            -KEY_LINES:
        ]
    covered = [(item.start_line, item.end_line) for item in evidence if item.source_type == "log"]
    missing = tuple(n for n in key if not any(start <= n <= end for start, end in covered))
    if missing:
        notes.append(
            "The retrieved excerpts miss the failure line(s) "
            + ", ".join(f"L{n}" for n in missing)
            + "."
        )
        return Completeness("missing_lines", key, missing, tuple(notes))
    return Completeness("sufficient", key, (), tuple(notes))
