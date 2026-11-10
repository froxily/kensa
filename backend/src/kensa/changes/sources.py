"""Where change facts come from (v1.1, D-054).

* ``GitHubChangeSource``: read-only, through the pinned ``GitHubClient`` (GET only, paths under
  ``/repos/``), bounded by a small request budget. Commit messages and authors are never kept.
* ``FixtureChangeSource``: an evaluation case's ``runs.json``, ``history.json`` and
  ``baseline.log``, reduced to exactly what GitHub's compare API would give (files over the
  whole range, not per commit), so evaluation measures what a live run can know.
"""

import json
import re
from pathlib import Path
from typing import Any

from kensa.changes.model import Comparison, FileChange, JobFacts, RunFacts
from kensa.github.client import GitHubClient, GitHubError
from kensa.github.importer import FetchedFile, GitHubImport, decode_log
from kensa.history.github import BudgetExhaustedError, RequestBudget, parse_time

MAX_CANDIDATES = 6
MAX_FILES = 300
MAX_PATCH_CHARS = 20_000
JOB_FETCHES = 2
_SHA = re.compile(r"^[0-9a-f]{40}$")


def _labels(value: Any) -> tuple[str, ...] | None:
    if not isinstance(value, list):
        return None
    return tuple(str(v)[:100] for v in value[:20])


def _job(data: dict[str, Any]) -> JobFacts:
    return JobFacts(
        name=str(data.get("name") or "")[:300],
        conclusion=data.get("conclusion"),
        labels=_labels(data.get("labels")),
        runner_image=data.get("runner_image"),
        runner_image_version=data.get("runner_image_version"),
        job_id=int(data["id"]) if data.get("id") else None,
    )


def _run(data: dict[str, Any], jobs: tuple[JobFacts, ...] | None) -> RunFacts:
    return RunFacts(
        run_id=int(data.get("run_id") or data.get("id") or 0),
        run_attempt=int(data.get("run_attempt") or 1),
        workflow_path=str(data.get("workflow_path") or data.get("path") or "")[:300],
        event=str(data.get("event") or "")[:50],
        head_branch=data.get("head_branch"),
        head_sha=str(data.get("head_sha") or ""),
        created_at=parse_time(data.get("created_at")),
        conclusion=data.get("conclusion"),
        jobs=jobs,
    )


def _file(data: dict[str, Any]) -> FileChange:
    patch = data.get("patch")
    return FileChange(
        path=str(data.get("filename") or data.get("path") or "")[:500],
        status=str(data.get("status") or "modified")[:20],
        previous_path=data.get("previous_filename") or data.get("previous_path"),
        additions=int(data.get("additions") or 0),
        deletions=int(data.get("deletions") or 0),
        patch=str(patch)[:MAX_PATCH_CHARS] if isinstance(patch, str) else None,
    )


def merge_file_changes(changes: list[FileChange]) -> list[FileChange]:
    """One entry per path over the whole range, as GitHub's compare API reports files."""
    merged: dict[str, FileChange] = {}
    for change in changes:
        earlier = merged.get(change.path)
        if earlier is None:
            merged[change.path] = change
            continue
        patch = "\n".join(p for p in (earlier.patch, change.patch) if p)
        merged[change.path] = FileChange(
            path=change.path,
            status="added" if earlier.status == "added" else change.status,
            previous_path=earlier.previous_path or change.previous_path,
            additions=earlier.additions + change.additions,
            deletions=earlier.deletions + change.deletions,
            patch=patch[:MAX_PATCH_CHARS] or None,
        )
    return list(merged.values())


# ---------------------------------------------------------------------- evaluation fixture ---


class FixtureChangeSource:
    """An evaluation case's facts (``eval/datasets/v3-change``), read-only."""

    def __init__(self, case_dir: Path) -> None:
        self.case_dir = case_dir
        self.runs = json.loads((case_dir / "runs.json").read_text(encoding="utf-8-sig"))
        self.history = json.loads((case_dir / "history.json").read_text(encoding="utf-8-sig"))

    def failed(self) -> tuple[RunFacts, str]:
        data = self.runs["failed"]
        jobs = tuple(_job(j) for j in data.get("jobs") or [])
        return _run(data, jobs), str(data.get("failed_job") or (jobs[0].name if jobs else ""))

    def candidates(self, failed: RunFacts, job_name: str) -> list[RunFacts]:
        return [
            _run(c, tuple(_job(j) for j in c["jobs"]) if c.get("jobs") is not None else None)
            for c in self.runs.get("candidates") or []
        ]

    def compare(self, base_sha: str, head_sha: str) -> Comparison:
        data = (self.history.get("comparisons") or {}).get(f"{base_sha}...{head_sha}")
        if not isinstance(data, dict) or data.get("error") or "status" not in data:
            return Comparison("not_found", None, (), (), False)
        commits = data.get("commits") or []
        files = [_file(f) for c in commits for f in c.get("files") or []]
        return Comparison(
            status=str(data["status"]),
            merge_base=data.get("merge_base"),
            commits=tuple(str(c.get("sha")) for c in commits),
            files=tuple(merge_file_changes(files)),
            truncated=bool(data.get("truncated")),
        )

    def workflow_blob(self, sha: str, path: str) -> str | None:
        blob = (self.history.get("workflow_blobs") or {}).get(sha)
        return str(blob) if blob else None

    def baseline_log(self, run: RunFacts, job_name: str) -> list[str] | None:
        path = self.case_dir / "baseline.log"
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8-sig").split("\n")


# ----------------------------------------------------------------------------- GitHub ---


class GitHubChangeSource:
    """Comparable earlier runs and the changes since, read from GitHub within a budget."""

    def __init__(
        self,
        client: GitHubClient,
        owner: str,
        repo: str,
        workflow_id: int | None,
        budget: RequestBudget,
        known_blobs: dict[tuple[str, str], str] | None = None,
    ) -> None:
        self.client, self.owner, self.repo = client, owner, repo
        self.workflow_id, self.budget = workflow_id, budget
        self.known_blobs = dict(known_blobs or {})

    def _get(self, path: str, params: dict[str, str | int] | None, what: str) -> Any:
        self.budget.spend()
        return self.client.get_json(path, params, what=what)

    def _jobs(self, run: dict[str, Any]) -> tuple[JobFacts, ...]:
        path = (
            f"/repos/{self.owner}/{self.repo}/actions/runs/{int(run['id'])}"
            f"/attempts/{int(run.get('run_attempt') or 1)}/jobs"
        )
        data = self._get(path, {"per_page": 100}, "jobs of an earlier run")
        items = data.get("jobs") or [] if isinstance(data, dict) else []
        return tuple(_job(j) for j in items if isinstance(j, dict))

    def candidates(self, failed: RunFacts, job_name: str) -> list[RunFacts]:
        if self.workflow_id is None:
            return []
        base = f"/repos/{self.owner}/{self.repo}/actions/workflows/{int(self.workflow_id)}/runs"
        found: dict[int, dict[str, Any]] = {}
        same: dict[str, str | int] = {"status": "success", "event": failed.event, "per_page": 3}
        if failed.head_branch:
            same["branch"] = failed.head_branch
        anywhere: dict[str, str | int] = {"status": "success", "per_page": 5}
        for params in (same, anywhere):
            data = self._get(base, params, "earlier successful runs")
            for run in (data.get("workflow_runs") or []) if isinstance(data, dict) else []:
                if isinstance(run, dict) and int(run.get("id") or 0) != failed.run_id:
                    found.setdefault(int(run["id"]), run)
        runs = sorted(
            (r for r in found.values() if r.get("repository", {}).get("private") is not True),
            key=lambda r: str(r.get("created_at") or ""),
            reverse=True,
        )
        if failed.created_at is not None:
            runs = [
                r
                for r in runs
                if (created := parse_time(r.get("created_at"))) is None
                or created < failed.created_at
            ]
        facts: list[RunFacts] = []
        fetched = 0
        for run in runs[:MAX_CANDIDATES]:
            matches = (
                str(run.get("path") or "") == failed.workflow_path
                and run.get("event") == failed.event
                and run.get("head_branch") == failed.head_branch
            )
            jobs: tuple[JobFacts, ...] | None = None
            if matches and fetched < JOB_FETCHES:
                jobs = self._jobs(run)
                fetched += 1
            facts.append(_run(run, jobs))
        return facts

    def compare(self, base_sha: str, head_sha: str) -> Comparison:
        if not (_SHA.match(base_sha) and _SHA.match(head_sha)):
            return Comparison("not_found", None, (), (), False)
        try:
            data = self._get(
                f"/repos/{self.owner}/{self.repo}/compare/{base_sha}...{head_sha}",
                {"per_page": 100},
                "the changes between the runs",
            )
        except GitHubError as exc:
            if exc.code in ("not_found", "gone") or exc.status == 422:
                return Comparison("not_found", None, (), (), False)
            raise
        if not isinstance(data, dict):
            return Comparison("not_found", None, (), (), False)
        commits = [c for c in data.get("commits") or [] if isinstance(c, dict)]
        files = [_file(f) for f in (data.get("files") or [])[:MAX_FILES] if isinstance(f, dict)]
        merge_base = (data.get("merge_base_commit") or {}).get("sha")
        total = int(data.get("total_commits") or len(commits))
        return Comparison(
            status=str(data.get("status") or "not_found")[:20],
            merge_base=merge_base if isinstance(merge_base, str) else None,
            commits=tuple(str(c.get("sha")) for c in commits),
            files=tuple(files),
            truncated=total > len(commits) or len(data.get("files") or []) >= MAX_FILES,
        )

    def workflow_blob(self, sha: str, path: str) -> str | None:
        if (sha, path) in self.known_blobs:
            return self.known_blobs[(sha, path)]
        self.budget.spend()
        data = self.client.file_at(self.owner, self.repo, path, sha)
        blob = data.get("sha") if data is not None else None
        return blob if isinstance(blob, str) else None

    def baseline_log(self, run: RunFacts, job_name: str) -> list[str] | None:
        """The baseline job's log, for its runner image. GitHub serves logs only to signed-in
        requests, so without a token this is unknown (and the runs only partially comparable)."""
        job = run.job(job_name)
        if job is None or job.job_id is None or not self.client.authenticated:
            return None
        try:
            self.budget.spend()
            download = self.client.job_log(self.owner, self.repo, job.job_id)
        except (GitHubError, BudgetExhaustedError):
            return None
        return decode_log(download.content).split("\n")[:200]


def failed_run_facts(imported: GitHubImport) -> tuple[RunFacts, str]:
    run, job = imported.run, imported.job
    facts = RunFacts(
        run_id=run.id,
        run_attempt=run.run_attempt,
        workflow_path=run.workflow_path,
        event=run.event,
        head_branch=run.head_branch,
        head_sha=run.head_sha,
        created_at=parse_time(run.created_at),
        conclusion=run.conclusion,
        jobs=(JobFacts(name=job.name, conclusion=job.conclusion, labels=job.labels),),
    )
    return facts, job.name


def known_blobs(files: list[FetchedFile], sha: str) -> dict[tuple[str, str], str]:
    return {(sha, f.path): f.blob_sha for f in files if f.blob_sha}
