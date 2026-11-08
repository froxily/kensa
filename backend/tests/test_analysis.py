import json
from pathlib import Path

import pytest

from kensa.analysis.classifier import classify
from kensa.analysis.signatures import extract_signatures
from kensa.ingestion.chunking import ERROR_AFTER, ERROR_BEFORE, STEP_WINDOW, chunk_log
from kensa.ingestion.normalize import normalize_log

FIXTURES = Path(__file__).resolve().parents[2] / "eval" / "fixtures" / "m0-benchmark"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))


def _lines(name: str) -> list[str]:
    return normalize_log((FIXTURES / name).read_text(encoding="utf-8")).text.split("\n")


@pytest.mark.parametrize(
    ("name", "expected"),
    [(f["file"], f["expected_category"]) for f in MANIFEST["fixtures"]],
)
def test_rules_classify_synthetic_fixtures(name: str, expected: str) -> None:
    # The fixtures were written alongside these rules: this guards the rules, it is not an
    # accuracy measurement (that needs the independent M2 dataset).
    result = classify(extract_signatures(_lines(name)))
    assert result.category == expected
    assert result.supporting_lines


def test_signature_values_are_extracted() -> None:
    sigs = extract_signatures(_lines("missing-env-var.log"))
    env = [s for s in sigs if s.rule_id == "env.missing"]
    assert [s.value for s in env] == ["VITE_API_BASE_URL"]
    assert env[0].line_number == 24
    assert any(s.rule_id == "exit.code" and s.value == "1" for s in sigs)


def test_unknown_when_no_categorised_signature() -> None:
    result = classify(extract_signatures(["all good", "##[error]something odd happened"]))
    assert result.category == "unknown"
    assert result.share == 0.0
    assert not result.is_strong


def test_ties_go_to_earliest_evidence() -> None:
    lines = ["No such file or directory: 'a.txt'", "connection refused somewhere else"]
    result = classify(extract_signatures(lines))
    # workflow_path (weight 2) beats db_connectivity's generic refused (weight 1).
    assert result.category == "workflow_path"


def test_prefilter_skips_noise_quickly() -> None:
    lines = [f"building module {i}" for i in range(20_000)] + ["npm error code ERESOLVE"]
    sigs = extract_signatures(lines)
    assert [s.value for s in sigs if s.kind == "npm_error_code"] == ["ERESOLVE"]


def test_chunking_covers_every_line_and_respects_steps() -> None:
    lines = _lines("dependency-resolution.log")
    sigs = extract_signatures(lines)
    chunks = chunk_log(lines, [s.line_number for s in sigs])
    steps = [c for c in chunks if c.kind == "step"]
    covered = {n for c in steps for n in range(c.start_line, c.end_line + 1)}
    assert covered == set(range(1, len(lines) + 1))
    assert steps[0].step_name == "Run npm ci"
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    for chunk in chunks:
        assert chunk.content == "\n".join(lines[chunk.start_line - 1 : chunk.end_line])


def test_error_windows_merge_and_are_bounded() -> None:
    lines = [f"line {i}" for i in range(1, 201)]
    windows = [c for c in chunk_log(lines, [50, 52, 150]) if c.kind == "error_window"]
    assert [(c.start_line, c.end_line) for c in windows] == [
        (50 - ERROR_BEFORE, 52 + ERROR_AFTER),
        (150 - ERROR_BEFORE, 150 + ERROR_AFTER),
    ]


def test_long_steps_are_windowed() -> None:
    lines = ["##[group]Run big"] + [f"out {i}" for i in range(STEP_WINDOW * 2)]
    steps = [c for c in chunk_log(lines, []) if c.kind == "step"]
    assert len(steps) == 3
    assert all(c.end_line - c.start_line + 1 <= STEP_WINDOW for c in steps)
    assert all(c.step_name == "Run big" for c in steps)
