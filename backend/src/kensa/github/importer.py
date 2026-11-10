"""Turning a public GitHub Actions run into Kensa evidence (M4, D-031, D-033).

Read-only and commit-pinned:
* The run is read once; its ``head_sha`` pins every repository file fetched for it, and the files
  are stored in a repository snapshot for that commit, so evidence always shows the code the run
  executed, never a later version.
* Only failed jobs are offered. A job's failed steps come from GitHub's own step conclusions.
* The log comes from GitHub (with a token) or is pasted by the user (for example when logs need
  sign-in or have expired). Logs larger than Kensa's limits keep their end, where the failure is,
  and say so on their first line.
* Source files are chosen from paths the log mentions near failure lines, within the run's
  workspace only. Nothing that is downloaded is ever executed.
"""

import base64
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from kensa.analysis.indicators import FAILURE_MARKER
from kensa.github.client import GitHubClient, GitHubError
from kensa.github.urls import GitHubRef
from kensa.ingestion.files import source_type_for
from kensa.ingestion.normalize import MAX_LINES, MAX_LOG_BYTES, strip_timestamp

INVESTIGABLE_RUNS = frozenset({"failure", "timed_out", "startup_failure", "cancelled"})
FAILED_JOBS = frozenset({"failure", "timed_out", "cancelled"})
MAX_FILE_BYTES = 200_000
LOG_HEADROOM = 2_000  # bytes kept free for the truncation notice
NEAR_FAILURE = 3

_PATH = re.compile(
    r"(?<![\w/.\\-])((?:[A-Za-z]:)?[\w./\\@+-]*?[\w@+-]\."
    r"(?:py|pyi|js|mjs|cjs|jsx|ts|tsx|go|rs|java|kt|rb|php|cs|swift|c|cc|cpp|h|hpp|"
    r"yml|yaml|toml|json|cfg|ini|sh|txt|lock|mod|gradle|xml|properties))(?![\w-])"
)
_WORKSPACE = re.compile(
    r"^(?:/home/runner/work|/Users/runner/work|[A-Za-z]:/a)/[^/]+/[^/]+/|^/github/workspace/"
)
_SKIP_SEGMENTS = frozenset(
    {
        "..",
        "site-packages",
        "dist-packages",
        "node_modules",
        ".venv",
        "venv",
        ".tox",
        ".nox",
        "__pycache__",
        ".git",
        "dist",
        "build",
        "_work",
        "hostedtoolcache",
    }
)
_SEGMENT = re.compile(r"^[\w.@+-]{1,100}$")


@dataclass(frozen=True)
class RepoInfo:
    owner: str
    repo: str
    html_url: str
    private: bool


@dataclass(frozen=True)
class RunInfo:
    id: int
    name: str
    display_title: str
    run_number: int
    run_attempt: int
    event: str
    status: str
    conclusion: str | None
    head_branch: str | None
    head_sha: str
    workflow_path: str
    html_url: str
    created_at: str
    workflow_id: int | None = None  # v1.1: finds comparable earlier runs


@dataclass(frozen=True)
class StepInfo:
    number: int
    name: str
    conclusion: str | None


@dataclass(frozen=True)
class JobInfo:
    id: int
    name: str
    conclusion: str | None
    html_url: str
    failed_steps: tuple[StepInfo, ...]
    labels: tuple[str, ...] | None = None  # v1.1: runner labels, for comparability


@dataclass(frozen=True)
class FetchedFile:
    path: str
    source_type: str
    content: str
    blob_sha: str | None = None  # v1.1: the file's version, for workflow-file identity


@dataclass
class GitHubImport:
    repo: RepoInfo
    run: RunInfo
    job: JobInfo
    log_text: str
    log_source: str  # "github" | "pasted"
    log_dropped_lines: int
    files: list[FetchedFile] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)


# ------------------------------------------------------------------------------- parsing ---


def _repo(data: dict[str, Any], ref: GitHubRef) -> RepoInfo:
    repository = data.get("repository") or {}
    return RepoInfo(
        owner=ref.owner,
        repo=ref.repo,
        html_url=f"https://github.com/{ref.owner}/{ref.repo}",
        private=bool(repository.get("private", False)),
    )


def run_info(data: dict[str, Any]) -> RunInfo:
    return RunInfo(
        id=int(data["id"]),
        name=str(data.get("name") or ""),
        display_title=str(data.get("display_title") or "")[:300],
        run_number=int(data.get("run_number") or 0),
        run_attempt=int(data.get("run_attempt") or 1),
        event=str(data.get("event") or ""),
        status=str(data.get("status") or ""),
        conclusion=data.get("conclusion"),
        head_branch=data.get("head_branch"),
        head_sha=str(data["head_sha"]),
        workflow_path=str(data.get("path") or ""),
        html_url=str(data.get("html_url") or ""),
        created_at=str(data.get("created_at") or ""),
        workflow_id=int(data["workflow_id"]) if data.get("workflow_id") else None,
    )


def job_info(data: dict[str, Any]) -> JobInfo:
    steps = tuple(
        StepInfo(int(s.get("number") or 0), str(s.get("name") or ""), s.get("conclusion"))
        for s in data.get("steps") or []
        if s.get("conclusion") in FAILED_JOBS
    )
    return JobInfo(
        id=int(data["id"]),
        name=str(data.get("name") or "")[:200],
        conclusion=data.get("conclusion"),
        html_url=str(data.get("html_url") or ""),
        failed_steps=steps,
        labels=tuple(str(label)[:100] for label in (data.get("labels") or [])[:20])
        if isinstance(data.get("labels"), list)
        else None,
    )


# ------------------------------------------------------------------------------- reading ---


def failed_runs(client: GitHubClient, ref: GitHubRef, limit: int = 10) -> list[RunInfo]:
    data = client.get_json(
        f"/repos/{ref.owner}/{ref.repo}/actions/runs",
        {"status": "failure", "per_page": limit},
        what=f"workflow runs of {ref.full_name}",
    )
    runs = data.get("workflow_runs") or [] if isinstance(data, dict) else []
    if runs and runs[0].get("repository", {}).get("private"):
        raise GitHubError("private_repository", "Kensa only reads public repositories.", 422)
    return [run_info(r) for r in runs]


def load_run(client: GitHubClient, ref: GitHubRef) -> tuple[RepoInfo, RunInfo, list[JobInfo]]:
    if ref.run_id is None:
        raise GitHubError("invalid_url", "This URL does not name a workflow run.", 422)
    base = f"/repos/{ref.owner}/{ref.repo}/actions/runs/{ref.run_id}"
    if ref.attempt is not None:
        base += f"/attempts/{ref.attempt}"
    data = client.get_json(base, what=f"run {ref.run_id} of {ref.full_name}")
    if not isinstance(data, dict) or "head_sha" not in data:
        raise GitHubError("upstream_error", "GitHub sent an unexpected run description.")
    repo, run = _repo(data, ref), run_info(data)
    if repo.private:
        raise GitHubError("private_repository", "Kensa only reads public repositories.", 422)
    if run.status != "completed":
        raise GitHubError(
            "run_in_progress", "This run has not finished yet; investigate it once it has.", 409
        )
    if run.conclusion not in INVESTIGABLE_RUNS:
        raise GitHubError(
            "run_not_failed", f"This run did not fail (conclusion: {run.conclusion}).", 409
        )
    jobs = client.get_json(
        f"{base}/jobs",
        {"filter": "latest", "per_page": 100} if ref.attempt is None else {"per_page": 100},
        what=f"jobs of run {ref.run_id}",
    )
    failed = [
        job_info(j)
        for j in (jobs.get("jobs") or [] if isinstance(jobs, dict) else [])
        if j.get("conclusion") in FAILED_JOBS
    ]
    return repo, run, failed


def select_job(jobs: list[JobInfo], job_id: int | None) -> JobInfo:
    if not jobs:
        raise GitHubError("no_failed_jobs", "This run has no failed job to investigate.", 409)
    if job_id is None:
        return jobs[0]
    for job in jobs:
        if job.id == job_id:
            return job
    raise GitHubError("job_not_failed", "That job is not one of this run's failed jobs.", 409)


# ------------------------------------------------------------------------------------ log ---


def fit_log(text: str) -> tuple[str, int]:
    """Keep the end of an over-long log (the failure is there) and say what was dropped."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    budget = MAX_LOG_BYTES - LOG_HEADROOM
    kept: list[str] = []
    size = 0
    for line in reversed(lines):
        cost = len(line.encode("utf-8", "replace")) + 1
        if size + cost > budget or len(kept) >= MAX_LINES - 1:
            break
        kept.append(line)
        size += cost
    dropped = len(lines) - len(kept)
    if dropped == 0:
        return "\n".join(lines), 0
    notice = (
        f"[Kensa: the first {dropped} lines of this job log were truncated to fit the "
        f"{MAX_LOG_BYTES // 1_000_000} MB limit]"
    )
    return "\n".join([notice, *reversed(kept)]), dropped


def decode_log(content: bytes) -> str:
    return content.decode("utf-8", errors="replace").lstrip("﻿")


# ---------------------------------------------------------------------------------- files ---


def repo_path(candidate: str) -> str | None:
    """A repository-relative path from a path in a log, or None if it is outside the run's
    workspace (system or dependency files) or not a plausible repository path."""
    path = candidate.replace("\\", "/")
    path = _WORKSPACE.sub("", path)
    if "://" in path or path.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", path):
        return None
    while path.startswith("./"):
        path = path[2:]
    segments = path.split("/")
    if not path or len(path) > 200 or len(segments) > 12:
        return None
    if any(s in _SKIP_SEGMENTS or not _SEGMENT.match(s) for s in segments):
        return None
    return path


def referenced_paths(log_text: str, limit: int) -> list[str]:
    """Paths the log mentions, those on or near failure lines first."""
    lines = [strip_timestamp(line) for line in log_text.split("\n")]
    near: set[int] = set()
    for index, line in enumerate(lines):
        if FAILURE_MARKER.search(line):
            near.update(range(max(0, index - NEAR_FAILURE), index + NEAR_FAILURE + 1))
    first_seen: dict[str, int] = {}
    priority: Counter[str] = Counter()
    for index, line in enumerate(lines):
        for match in _PATH.finditer(line):
            path = repo_path(match.group(1))
            if path is None:
                continue
            first_seen.setdefault(path, index)
            priority[path] += 10 if index in near else 1
    ranked = sorted(priority, key=lambda p: (-priority[p], first_seen[p]))
    return ranked[:limit]


def _decode_file(data: dict[str, Any]) -> str | None:
    if data.get("type") != "file" or data.get("encoding") != "base64":
        return None
    if int(data.get("size") or 0) > MAX_FILE_BYTES:
        return None
    try:
        raw = base64.b64decode(str(data.get("content") or ""), validate=False)
        text = raw.decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    return None if "\x00" in text else text


def fetch_files(
    client: GitHubClient, repo: RepoInfo, sha: str, paths: list[str]
) -> tuple[list[FetchedFile], list[str]]:
    files: list[FetchedFile] = []
    missing: list[str] = []
    for path in paths:
        data = client.file_at(repo.owner, repo.repo, path, sha)
        text = _decode_file(data) if data is not None else None
        if text is None:
            missing.append(path)
            continue
        blob = data.get("sha") if data is not None else None
        files.append(
            FetchedFile(path, source_type_for(path), text, blob if isinstance(blob, str) else None)
        )
    return files, missing


# --------------------------------------------------------------------------------- import ---


def import_run(
    client: GitHubClient,
    ref: GitHubRef,
    *,
    job_id: int | None,
    pasted_log: str | None,
    max_files: int,
) -> GitHubImport:
    """Everything an investigation of one failed job needs. Network only; no database."""
    repo, run, jobs = load_run(client, ref)
    job = select_job(jobs, job_id)
    if pasted_log is not None and pasted_log.strip():
        raw, source = pasted_log, "pasted"
    else:
        raw, source = decode_log(client.job_log(repo.owner, repo.repo, job.id).content), "github"
    log_text, dropped = fit_log(raw)

    paths: list[str] = []
    if run.workflow_path.startswith(".github/workflows/"):
        paths.append(run.workflow_path)
    paths += [p for p in referenced_paths(log_text, max_files) if p not in paths]
    files, missing = fetch_files(client, repo, run.head_sha, paths)
    return GitHubImport(repo, run, job, log_text, source, dropped, files, missing)
