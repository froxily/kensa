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
# Only the dev split is read; the test split is spent and stays untouched.
DEV = load_cases(ROOT / "eval" / "datasets" / "v2", "dev")
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


def stored_log(run: Run) -> list[str]:
    (document,) = run["documents"]
    lines: list[str] = recording()["documents"][f"{run['id']}/{document['id']}"]["lines"]
    return lines


def file_lines(path: Path) -> list[str]:
    return [TIMESTAMP.sub("", line) for line in path.read_text(encoding="utf-8").splitlines()]


def dev_case(run: Run) -> Path:
    """The v2 dev case whose log this upload is (the recording keeps no case id or title)."""
    log = stored_log(run)
    matches = [case.folder for case in DEV if file_lines(case.log_path) == log]
    assert len(matches) == 1, f"{run_id(run)}: matches {len(matches)} cases"
    return matches[0]


def source_lines(run: Run, item: Run) -> list[str]:
    name = item["document_name"]
    if item["source_type"] == "log":
        return stored_log(run)
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
    sources = sorted(run["source"] for run in runs())
    assert sources == ["sample"] * 3 + ["upload"] * 3
    samples = sorted(run["documents"][0]["name"] for run in runs() if run["source"] == "sample")
    assert samples == sorted(path.name for path in SAMPLES.glob("*.log"))
    cases = sorted(dev_case(run).name for run in runs() if run["source"] == "upload")
    assert cases == sorted(recorder.DEV_CASES)


def test_stored_logs_are_the_source_logs() -> None:
    for run in runs():
        (document,) = run["documents"]
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
    assert checked == 20


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
