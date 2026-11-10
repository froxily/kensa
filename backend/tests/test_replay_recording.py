"""The committed replay recording matches the files its runs read (M6).

An independent check, written without Kensa's verifier or ingestion code: every recorded log
line, evidence block, error signature and citation is compared with the source files. A recording
that was edited by hand, or that no longer matches the samples, the knowledge notes or the
evaluation cases, fails here. ``record_replays.py --verify`` separately compares it with the runs
stored in the ``kensa_replay`` database.
"""

import importlib
import json
import re
import sys
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from kensa.evaluation.dataset import load_cases

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
recorder = importlib.import_module("record_replays")

RECORDING = ROOT / "frontend" / "replay" / "recording.json"
SAMPLES = ROOT / "backend" / "src" / "kensa" / "samples"
KNOWLEDGE = ROOT / "knowledge"
# Only dev splits are read; test splits stay untouched.
DEV = load_cases(ROOT / "eval" / "datasets" / "v2", "dev")
# Format 2 (v1.1): one synthetic v3-change dev case, recorded with its change analysis.
CHANGE_CASE = ROOT / "eval" / "datasets" / "v3-change" / "cases" / recorder.CHANGE_CASE
# GitHub Actions prefixes every log line with a timestamp; Kensa stores lines without it.
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z ?")
Run = dict[str, Any]


@cache
def recording() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(RECORDING.read_text(encoding="utf-8"))
    return data


def runs() -> list[Run]:
    investigations: list[Run] = recording()["investigations"]
    return investigations


def run_id(run: Run) -> str:
    return str(run["id"])[:8]


def log_document(run: Run) -> Run:
    """The run's log; a change-aware run also holds its diff documents (``diff/...``)."""
    documents: list[Run] = run["documents"]
    (document,) = [d for d in documents if not str(d["name"]).startswith("diff/")]
    return document


def stored_log(run: Run) -> list[str]:
    document = log_document(run)
    lines: list[str] = recording()["documents"][f"{run['id']}/{document['id']}"]["lines"]
    return lines


def file_lines(path: Path) -> list[str]:
    return [TIMESTAMP.sub("", line) for line in path.read_text(encoding="utf-8").splitlines()]


def case_logs() -> list[tuple[Path, Path]]:
    """Every evaluation case the recording may hold: (folder, log file)."""
    return [(case.folder, case.log_path) for case in DEV] + [
        (CHANGE_CASE, CHANGE_CASE / "failed.log")
    ]


def dev_case(run: Run) -> Path:
    """The dev case whose log this upload is (the recording keeps no case id or title)."""
    log = stored_log(run)
    matches = [folder for folder, path in case_logs() if file_lines(path) == log]
    assert len(matches) == 1, f"{run_id(run)}: matches {len(matches)} cases"
    return matches[0]


def patch_lines(folder: Path, path: str) -> set[str]:
    """Every line of every recorded patch of ``path`` in a v3-change case's history."""
    history = json.loads((folder / "history.json").read_text(encoding="utf-8-sig"))
    found: set[str] = set()
    for comparison in (history.get("comparisons") or {}).values():
        for commit in comparison.get("commits") or []:
            for change in commit.get("files") or []:
                if (change.get("filename") or change.get("path")) == path:
                    found.update((change.get("patch") or "").split("\n"))
    return found


def source_lines(run: Run, item: Run) -> list[str]:
    name = item["document_name"]
    if item["source_type"] == "log":
        return stored_log(run)
    if item["source_type"] == "diff":
        # Kensa's diff document joins the patch hunks of one path; each line is a patch line.
        lines: list[str] = item["lines"]
        assert set(lines) <= patch_lines(dev_case(run), name.removeprefix("diff/"))
        return lines
    if item["source_type"] == "kb":
        assert name.startswith("kb/")
        return file_lines(KNOWLEDGE / name.removeprefix("kb/"))
    # Code and workflow files come from the case's repository, at the path Kensa shows.
    return file_lines(dev_case(run) / "repo" / name)


def normal(text: str, *, markdown: bool) -> str:
    if markdown:
        text = text.replace("`", "").replace("*", "")
    return " ".join(TIMESTAMP.sub("", text).split()).casefold()


def test_the_recording_holds_the_planned_runs() -> None:
    assert recording()["format"] == 2
    sources = sorted(run["source"] for run in runs())
    assert sources == ["sample"] * 3 + ["upload"] * 4
    samples = sorted(run["documents"][0]["name"] for run in runs() if run["source"] == "sample")
    assert samples == sorted(path.name for path in SAMPLES.glob("*.log"))
    cases = sorted(dev_case(run).name for run in runs() if run["source"] == "upload")
    assert cases == sorted([*recorder.DEV_CASES, recorder.CHANGE_CASE])


def test_only_the_synthetic_change_case_has_a_change_analysis() -> None:
    changes = recording()["changes"]
    assert set(changes) == {run["id"] for run in runs()}
    with_analysis = [run for run in runs() if changes[run["id"]] is not None]
    assert [dev_case(run).name for run in with_analysis] == [recorder.CHANGE_CASE]
    (analysis,) = (changes[run["id"]] for run in with_analysis)
    # D-054: a suspect is a correlation, never a cause.
    assert {s["status"] for s in analysis["suspects"]} <= {"correlated", "weak"}
    label = json.loads((CHANGE_CASE / "case.json").read_text(encoding="utf-8-sig"))
    assert analysis["comparability"] == label["comparability"]


def test_every_run_has_its_similar_failures_and_the_dashboard_counts_them() -> None:
    history = recording()["history"]
    assert set(history) == {run["id"] for run in runs()}
    for run in runs():
        # v1.1.0: recorded in the default settings, where history matching is off (D-057):
        # no match, count or recurrence claim, but the fingerprints are recorded.
        entry = history[run["id"]]
        assert entry["matching"] is False, run_id(run)
        assert entry["similar"] == [], run_id(run)
        # A log that shows no failure (the abstention) has no signature, so no fingerprint.
        assert bool(entry["fingerprints"]) == bool(run["signatures"]), run_id(run)
        assert all(fp["occurrences"] is None for fp in entry["fingerprints"]), run_id(run)
        assert {fp["kind"] for fp in entry["fingerprints"]} <= {"exact", "approximate"}
        for item in history[run["id"]]["similar"]:
            assert item["investigation_id"] != run["id"], run_id(run)  # never itself
    summary = recording()["analytics"]["summary"]
    assert summary["investigations"] == len(runs())
    assert recording()["analytics"]["history_matching"] is False
    assert summary["recurring_failures"] is None
    assert recording()["analytics"]["recurring"] == []
    assert recording()["repositories"] == []


def test_stored_logs_are_the_source_logs() -> None:
    for run in runs():
        document = log_document(run)
        assert document["redaction_count"] == 0, run_id(run)
        if run["source"] == "sample":
            assert stored_log(run) == file_lines(SAMPLES / document["name"]), run_id(run)
        else:
            dev_case(run)  # exactly one case has this log


def test_every_evidence_block_quotes_its_file() -> None:
    for run in runs():
        for item in run["evidence"]:
            source = source_lines(run, item)
            expected = source[item["start_line"] - 1 : item["end_line"]]
            assert item["lines"] == expected, f"{run_id(run)} {item['label']}"


def test_every_signature_is_on_its_line() -> None:
    for run in runs():
        log = stored_log(run)
        for signature in run["signatures"]:
            assert signature["excerpt"] in log[signature["line_number"] - 1], run_id(run)


def test_every_citation_quotes_its_cited_line() -> None:
    checked = 0
    for run in runs():
        evidence = {item["label"]: item for item in run["evidence"]}
        for citation in (run["diagnosis"] or {}).get("citations", []):
            item = evidence[citation["evidence_label"]]
            line = citation["line_number"]
            assert item["start_line"] <= line <= item["end_line"], run_id(run)
            markdown = item["source_type"] == "kb"
            found = normal(citation["quote"], markdown=markdown) in normal(
                item["lines"][line - item["start_line"]], markdown=markdown
            )
            assert found == citation["valid"], f"{run_id(run)} {citation['evidence_label']} L{line}"
            checked += 1
    assert checked == 24  # every citation of the format-2 recording (7 runs)


@pytest.mark.parametrize("field", ["category", "verification_status"])
def test_the_report_agrees_with_its_diagnosis(field: str) -> None:
    for run in runs():
        assert run[field] == run["diagnosis"][field], run_id(run)


def test_statuses_follow_the_rules() -> None:
    manifest = recording()["manifest"]
    for run in runs():
        diagnosis = run["diagnosis"]
        assert run["provider"] == diagnosis["provider"] == "ollama", run_id(run)
        assert diagnosis["model"] == manifest["model"], run_id(run)
        # D-046: a failing test is a symptom, never a corroborated cause.
        if run["category"] == "test_regression":
            assert run["verification_status"] != "corroborated", run_id(run)
        if run["verification_status"] == "not_established":
            assert run["category"] == "unknown", run_id(run)
            assert run["proposals"] == [], run_id(run)
        # No decision is recorded: the replay's approval flow starts fresh.
        assert run["decision"] is None, run_id(run)
        assert {p["status"] for p in run["proposals"]} <= {"proposed", "withdrawn"}, run_id(run)


def test_the_recording_is_publishable() -> None:
    assert recorder.check_recording(recording()) == []
