"""Files the app, its evaluation or its demo read must be in git, or a fresh clone breaks (M6).

The M6 fresh-clone check found the built-in sample logs missing from every clone: `*.log` in
.gitignore had kept them out of git since M1, while every local test passed because the files
existed in the working copy.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
READ_AT_RUNTIME = [
    "backend/src",
    "backend/alembic",
    "eval/datasets",
    "eval/fixtures",
    "knowledge",
    "frontend/src",
    "frontend/replay",
]
CACHES = ("__pycache__", ".pyc", ".mypy_cache", ".ruff_cache", ".pytest_cache")


def test_nothing_the_app_or_its_evaluation_reads_is_git_ignored() -> None:
    git = shutil.which("git")
    if git is None or not (REPO_ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    ignored = subprocess.run(  # noqa: S603  (fixed argv built in this file)
        [git, "ls-files", "--others", "--ignored", "--exclude-standard", "--", *READ_AT_RUNTIME],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert [path for path in ignored if not any(cache in path for cache in CACHES)] == []
