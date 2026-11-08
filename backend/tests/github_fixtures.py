"""Sanitized GitHub API fixtures for M4 tests.

Shapes follow real api.github.com responses observed on 2026-10-30 (runs, jobs, contents, the
log redirect). Every identifying value is invented: owner, repository, ids, commit, URLs and the
log text. Tests never call the real API; respx refuses any request that is not mocked.
"""

import base64
from typing import Any

OWNER = "kensa-fixtures"
REPO = "demo-app"
RUN_ID = 9100000001
JOB_ID = 9200000001
OK_JOB_ID = 9200000002
SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER_SHA = "fedcba9876543210fedcba9876543210fedcba98"
API = "https://api.github.com"
RUN_PATH = f"/repos/{OWNER}/{REPO}/actions/runs/{RUN_ID}"
JOBS_PATH = f"{RUN_PATH}/jobs"
LOGS_PATH = f"/repos/{OWNER}/{REPO}/actions/jobs/{JOB_ID}/logs"
STORE_HOST = "productionresultssa7.blob.core.windows.net"
SIGNATURE = "sig=FAKE-SIGNED-SECRET-0123456789"
STORE_URL = (
    f"https://{STORE_HOST}/actions-results/00000000-1111/workflow-job-run-2222/logs/job/"
    f"job-logs.txt?rsct=text%2Fplain&se=2026-10-30T10%3A00%3A00Z&{SIGNATURE}&sp=r&sv=2025-01-05"
)
RUN_URL = f"https://github.com/{OWNER}/{REPO}/actions/runs/{RUN_ID}"

WORKFLOW = """name: test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Run tests
        run: python -m pytest -q
"""
CONFIG_PY = """import os


def database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        raise RuntimeError("Missing required environment variable: DATABASE_URL")
    return value
"""
T = "2026-10-28T08:01:0"
LOG = (
    "\n".join(
        [
            f"{T}0.1000000Z ##[group]Run actions/checkout@v4",
            f"{T}0.2000000Z Syncing repository: kensa-fixtures/demo-app",
            f"{T}1.0000000Z ##[endgroup]",
            f"{T}2.0000000Z ##[group]Run python -m pytest -q",
            f"{T}2.1000000Z python -m pytest -q",
            f"{T}2.2000000Z shell: /usr/bin/bash -e {{0}}",
            f"{T}2.3000000Z ##[endgroup]",
            f"{T}5.0000000Z ImportError while loading conftest "
            "'/home/runner/work/demo-app/demo-app/tests/conftest.py'.",
            f"{T}5.1000000Z tests/conftest.py:4: in <module>",
            f"{T}5.2000000Z     URL = database_url()",
            f'{T}5.3000000Z   File "/home/runner/work/demo-app/demo-app/src/demo/config.py", '
            "line 7, in database_url",
            f'{T}5.4000000Z     raise RuntimeError("Missing required environment variable: '
            'DATABASE_URL")',
            f'{T}5.5000000Z   File "/opt/hostedtoolcache/Python/3.12.7/x64/lib/python3.12/'
            'site-packages/_pytest/config/__init__.py", line 9, in load',
            f"{T}5.6000000Z RuntimeError: Missing required environment variable: DATABASE_URL",
            f"{T}5.7000000Z See https://docs.example.invalid/setup.py for help",
            f"{T}6.0000000Z ##[error]Process completed with exit code 4.",
            f"{T}7.0000000Z Post job cleanup.",
        ]
    )
    + "\n"
)


def run_json(**override: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": RUN_ID,
        "name": "test",
        "display_title": "Read the database URL from the environment",
        "run_number": 42,
        "run_attempt": 1,
        "event": "push",
        "status": "completed",
        "conclusion": "failure",
        "head_branch": "main",
        "head_sha": SHA,
        "path": ".github/workflows/test.yml",
        "html_url": RUN_URL,
        "created_at": "2026-10-28T08:00:41Z",
        "repository": {"full_name": f"{OWNER}/{REPO}", "private": False},
    }
    data.update(override)
    return data


def jobs_json() -> dict[str, Any]:
    return {
        "total_count": 2,
        "jobs": [
            {
                "id": JOB_ID,
                "name": "test",
                "status": "completed",
                "conclusion": "failure",
                "html_url": f"{RUN_URL}/job/{JOB_ID}",
                "steps": [
                    {"number": 1, "name": "Set up job", "conclusion": "success"},
                    {"number": 2, "name": "Run actions/checkout@v4", "conclusion": "success"},
                    {"number": 4, "name": "Run tests", "conclusion": "failure"},
                    {"number": 5, "name": "Post Run actions/checkout@v4", "conclusion": "success"},
                ],
            },
            {
                "id": OK_JOB_ID,
                "name": "lint",
                "status": "completed",
                "conclusion": "success",
                "html_url": f"{RUN_URL}/job/{OK_JOB_ID}",
                "steps": [],
            },
        ],
    }


def runs_json() -> dict[str, Any]:
    return {"total_count": 1, "workflow_runs": [run_json()]}


def contents_json(path: str, text: str) -> dict[str, Any]:
    raw = text.encode("utf-8")
    return {
        "type": "file",
        "encoding": "base64",
        "size": len(raw),
        "name": path.rsplit("/", 1)[-1],
        "path": path,
        "content": base64.encodebytes(raw).decode("ascii"),
    }
