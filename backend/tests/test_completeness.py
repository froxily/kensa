import uuid

from kensa.agents.completeness import assess, scan_log
from kensa.agents.evidence import EvidenceItem
from kensa.analysis.classifier import classify
from kensa.analysis.signatures import extract_signatures

FAILED_LOG = [
    "##[group]Run npm run build",
    "> vite build",
    "Error: Missing required environment variable: VITE_API_BASE_URL",
    "##[endgroup]",
    "##[error]Process completed with exit code 1.",
    "##[group]Post Run actions/checkout@v4",
    "Post job cleanup.",
    "##[endgroup]",
]
CUT_OFF_LOG = [
    "##[group]Run pytest",
    "collected 3 items",
    "tests/test_archive.py::test_name PASSED",
    "tests/test_archive.py::test_parent",
    "[log truncated]",
]


def _item(start: int, end: int, lines: list[str], source_type: str = "log") -> EvidenceItem:
    return EvidenceItem(
        label="E1",
        chunk_id=uuid.uuid4(),
        document_name="job.log",
        step_name=None,
        start_line=start,
        end_line=end,
        lines=tuple(lines[start - 1 : end]),
        score=0.1,
        channels=("tail",),
        source_type=source_type,
    )


def test_a_log_without_any_failure_is_reported_as_showing_none() -> None:
    signatures = extract_signatures(CUT_OFF_LOG)
    result = assess(
        scan_log(CUT_OFF_LOG), signatures, classify(signatures), [_item(1, 5, CUT_OFF_LOG)]
    )
    assert result.status == "no_failure_shown"
    assert "shows no failure" in result.notes[0]
    assert any("truncated (L5)" in note for note in result.notes)


def test_failure_lines_outside_the_evidence_are_missing() -> None:
    signatures = extract_signatures(FAILED_LOG)
    rule = classify(signatures)
    tail_only = [_item(6, 8, FAILED_LOG)]
    result = assess(scan_log(FAILED_LOG), signatures, rule, tail_only)
    assert result.status == "missing_lines"
    assert result.missing_lines == (3,)

    with_failure = [*tail_only, _item(1, 5, FAILED_LOG)]
    assert assess(scan_log(FAILED_LOG), signatures, rule, with_failure).status == "sufficient"


def test_only_log_evidence_counts_as_showing_the_failure_lines() -> None:
    signatures = extract_signatures(FAILED_LOG)
    note = [_item(1, 5, FAILED_LOG, source_type="kb")]
    result = assess(scan_log(FAILED_LOG), signatures, classify(signatures), note)
    assert result.status == "missing_lines"


def test_generic_failures_without_a_category_use_the_last_failure_lines() -> None:
    log = [
        "step one ok",
        "fatal: something odd happened",
        "##[error]Process completed with exit code 2.",
    ]
    signatures = extract_signatures(log)
    rule = classify(signatures)
    assert rule.category == "unknown"
    result = assess(scan_log(log), signatures, rule, [_item(1, 3, log)])
    assert result.status == "sufficient"
    assert result.key_lines == (2, 3)
