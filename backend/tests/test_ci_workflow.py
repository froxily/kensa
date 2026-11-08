"""The GitHub Actions workflows have never run on GitHub, so they are checked here: ci.yml must
run every check that scripts/ci-local.ps1 runs, both stay least-privilege, and every action is
pinned to a full commit SHA."""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
PAGES = ROOT / ".github" / "workflows" / "pages.yml"
CI_LOCAL = ROOT / "scripts" / "ci-local.ps1"
ALLOWED_ACTIONS = ("actions/checkout@", "actions/setup-node@", "astral-sh/setup-uv@")
PAGES_ACTIONS = ("actions/upload-pages-artifact@", "actions/deploy-pages@")
# `uses: owner/name@<40 hex> # vX.Y.Z`: a commit cannot be moved, unlike a tag.
PINNED = re.compile(r"^\s*(?:- )?uses: [\w.-]+/[\w.-]+@[0-9a-f]{40} # v\d+\.\d+\.\d+$")


@pytest.fixture(scope="module")
def workflow() -> dict[Any, Any]:
    loaded = yaml.safe_load(WORKFLOW.read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def steps(workflow: dict[Any, Any]) -> list[dict[str, Any]]:
    return [step for job in workflow["jobs"].values() for step in job["steps"]]


def test_every_local_check_is_mirrored(workflow: dict[Any, Any]) -> None:
    local = re.findall(r'Invoke-Step "[^"]+"\s+\$\w+ \{ (.+?) \}', CI_LOCAL.read_text("utf-8"))
    assert len(local) == 11
    commands = {step["run"] for step in steps(workflow) if "run" in step}
    assert set(local) <= commands


def test_the_workflow_is_least_privilege(workflow: dict[Any, Any]) -> None:
    text = WORKFLOW.read_text("utf-8")
    assert workflow["permissions"] == {"contents": "read"}
    # PyYAML (YAML 1.1) reads the bare key `on` as True.
    triggers: dict[str, Any] = workflow.get("on") or workflow[True]
    assert set(triggers) == {"push", "pull_request"}
    assert "pull_request_target" not in text
    assert not re.search(r"\$\{\{\s*secrets", text)
    assert "GITHUB_TOKEN" not in text
    for job in workflow["jobs"].values():
        assert "permissions" not in job
        assert job["timeout-minutes"] <= 30


def test_only_known_actions_without_persisted_credentials(workflow: dict[Any, Any]) -> None:
    for step in steps(workflow):
        if "uses" not in step:
            continue
        assert step["uses"].startswith(ALLOWED_ACTIONS)
        if step["uses"].startswith("actions/checkout@"):
            assert step["with"]["persist-credentials"] is False


def test_no_live_model_or_tracing(workflow: dict[Any, Any]) -> None:
    env = workflow["env"]
    assert env["KENSA_INFERENCE_PROVIDER"] == "mock"
    assert env["KENSA_EMBEDDING_PROVIDER"] == "mock"
    assert env["LANGSMITH_TRACING"] == "false"
    assert "127.0.0.1" in env["KENSA_DATABASE_URL"]


@pytest.mark.parametrize("path", [WORKFLOW, PAGES], ids=["ci", "pages"])
def test_every_action_is_pinned_to_a_commit(path: Path) -> None:
    lines = [line for line in path.read_text("utf-8").splitlines() if "uses:" in line]
    assert lines
    for line in lines:
        assert PINNED.match(line), line
    # The same action is pinned to the same commit everywhere.
    pins: dict[str, set[str]] = {}
    for workflow_path in (WORKFLOW, PAGES):
        for line in workflow_path.read_text("utf-8").splitlines():
            if match := re.search(r"uses: ([\w.-]+/[\w.-]+)@([0-9a-f]{40})", line):
                pins.setdefault(match[1], set()).add(match[2])
    assert all(len(commits) == 1 for commits in pins.values()), pins


def test_pages_runs_only_by_hand_and_writes_only_when_deploying() -> None:
    text = PAGES.read_text("utf-8")
    pages = yaml.safe_load(text)
    triggers: dict[str, Any] = pages.get("on") or pages[True]
    assert set(triggers) == {"workflow_dispatch"}
    assert pages["permissions"] == {"contents": "read"}
    assert "permissions" not in pages["jobs"]["build"]
    assert pages["jobs"]["deploy"]["permissions"] == {"pages": "write", "id-token": "write"}
    assert not re.search(r"\$\{\{\s*secrets", text)
    assert "pull_request" not in text
    build = pages["jobs"]["build"]["steps"]
    for step in build + pages["jobs"]["deploy"]["steps"]:
        if "uses" in step:
            assert step["uses"].startswith(ALLOWED_ACTIONS + PAGES_ACTIONS)
    checkout = next(step for step in build if step.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["persist-credentials"] is False
    # The replay ships its third-party notices.
    assert any("dist-replay/THIRD_PARTY_NOTICES.txt" in step.get("run", "") for step in build)
