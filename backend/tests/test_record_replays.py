"""The replay recorder refuses to write a recording that holds anything unpublishable (M6)."""

import importlib
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
recorder = importlib.import_module("record_replays")


def recording(**extra: object) -> dict[str, object]:
    return {
        "format": 1,
        "manifest": {"model": "qwen3:4b-instruct-2507-q4_K_M"},
        "investigations": [{"title": "Missing secret DEPLOY_TOKEN", "proposals": []}],
        "events": {"a": [{"summary": "Proposed missing_env_var with 2 citation(s)."}]},
        "documents": {},
        "samples": [],
        **extra,
    }


def test_a_clean_recording_passes() -> None:
    assert recorder.check_recording(recording()) == []


def test_secrets_signed_urls_and_local_paths_are_refused() -> None:
    token = "ghp_" + "a1B2c3D4e5F6g7H8i9J0" * 2
    found = recorder.check_recording(
        recording(
            documents={
                "a/doc": {"text": f"export GH_TOKEN={token}"},
                "a/url": {"text": "https://logs.example/job?sig=abcdef123456&se=2026"},
                "a/home": {"text": f"open {Path.home() / 'notes' / 'job.log'}"},
                "a/repo": {"text": f"cd {recorder.REPO_ROOT.as_posix()}/frontend"},
            }
        )
    )
    assert found == [
        "$.documents.a/doc.text: secret",
        "$.documents.a/url.text: signed_url",
        "$.documents.a/home.text: local path",
        "$.documents.a/repo.text: local path",
    ]


def test_ci_runner_paths_are_log_content_not_local_paths() -> None:
    runner = {"a/doc": {"text": "/home/runner/work/app/app/main.go:12: undefined: x"}}
    assert recorder.check_recording(recording(documents=runner)) == []


def test_verify_names_every_difference() -> None:
    committed = {"a": [1, {"b": "x"}], "c": "same", "d": [1, 2]}
    stored = {"a": [1, {"b": "y"}], "c": "same", "d": [1], "e": None}
    assert list(recorder.differences(committed, stored)) == ["$.a[1].b", "$.d"]
    assert list(recorder.differences(committed, committed)) == []
