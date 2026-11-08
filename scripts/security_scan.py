"""Read-only scan of stored data for secrets that should never be there (M5 security audit).

Runs Kensa's own redaction detectors over every stored text column (documents, chunks,
events, diagnoses, citations, proposals and their diffs, workflow runs) and over the local trace
files, and looks for signed log-URL query strings. Prints counts and row locations only, never
the matched values.

    uv run --directory backend --no-sync python ../scripts/security_scan.py
"""

import re
import sys

from sqlalchemy import text
from sqlalchemy.orm import Session

from kensa.core.config import REPO_ROOT, Settings
from kensa.db.session import build_engine
from kensa.ingestion.redaction import redact

SIGNED = re.compile(r"[?&](?:sig|se|sp|sv|rsct)=[^&\s\"']{4,}")
COLUMNS = {
    "documents": ["content", "name"],
    "chunks": ["content"],
    "agent_events": ["summary", "detail::text"],
    "diagnoses": [
        "summary",
        "root_cause",
        "uncertainty",
        "array_to_string(recommended_fixes, ' ')",
    ],
    "citations": ["quote"],
    "remediation_proposals": ["title", "action", "rationale", "diff"],
    "workflow_runs": ["html_url", "job_html_url"],
}


def findings(value: str) -> list[str]:
    found: list[str] = []
    if redact(value).total:
        found.append("secret")
    if SIGNED.search(value):
        found.append("signed_url")
    return found


def main() -> int:
    engine = build_engine(Settings())
    total = 0
    with Session(engine) as session:
        for table, columns in COLUMNS.items():
            rows = 0
            hits = 0
            for column in columns:
                for row in session.execute(text(f"SELECT id, {column} FROM {table}")):  # noqa: S608
                    rows += 1
                    found = findings(str(row[1] or ""))
                    if found:
                        hits += 1
                        print(f"  {table}.{column.split('::')[0]} id={row[0]}: {', '.join(found)}")
            print(f"{table}: {rows} values scanned, {hits} with findings")
            total += hits
    traces = list((REPO_ROOT / ".telemetry").rglob("*.jsonl*"))
    trace_hits = 0
    for path in traces:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            found = findings(line)
            if found:
                trace_hits += 1
                print(f"  {path.relative_to(REPO_ROOT)}:{number}: {', '.join(found)}")
    print(f"trace files: {len(traces)} scanned, {trace_hits} lines with findings")
    return 1 if total or trace_hits else 0


if __name__ == "__main__":
    sys.exit(main())
