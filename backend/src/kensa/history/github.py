"""Reading workflow history from GitHub (v1.1, D-052): read-only, budgeted and typed.

Every call goes through ``GitHubClient.get_json``: GET only, ``https://api.github.com`` only,
paths under ``/repos/`` only, size-capped, with the ETag cache. Nothing here downloads a log or
follows a redirect. Responses are parsed into small frozen records with every string capped, so
an unusual or hostile response cannot grow the database. Commit authors, e-mails and actor
logins are never read into these records (privacy, D-052).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from kensa.github.client import GitHubClient, GitHubError
from kensa.github.urls import check_name

PER_PAGE = 100
MAX_LIST_PAGES = 10  # GitHub's run listing stops at 1,000 results
MAX_JOB_PAGES = 3
MAX_STEPS = 100
FAILED_CONCLUSIONS = frozenset({"failure", "timed_out", "startup_failure", "cancelled"})


class BudgetExhaustedError(Exception):
    """The sync's request budget is used up; the cursor keeps its place for the next sync."""


class RequestBudget:
    """Counts GitHub requests (a 304 counts too) and stops a sync at its limit."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0

    @property
    def remaining(self) -> int:
        return self.limit - self.used

    def spend(self) -> None:
        if self.used >= self.limit:
            raise BudgetExhaustedError
        self.used += 1


@dataclass(frozen=True)
class RepositoryMeta:
    owner: str
    repo: str
    default_branch: str | None
    private: bool


@dataclass(frozen=True)
class RunRecord:
    run_id: int
    run_attempt: int
    run_number: int
    workflow_id: int
    workflow_path: str
    workflow_name: str
    event: str
    head_branch: str | None
    head_sha: str
    status: str
    conclusion: str | None
    created_at: datetime
    run_started_at: datetime | None
    updated_at: datetime | None
    private: bool

    @property
    def failed(self) -> bool:
        return self.conclusion in FAILED_CONCLUSIONS


@dataclass(frozen=True)
class StepRecord:
    number: int
    name: str
    conclusion: str | None
    started_at: str | None
    completed_at: str | None


@dataclass(frozen=True)
class JobRecord:
    job_id: int
    run_id: int
    run_attempt: int
    name: str
    status: str
    conclusion: str | None
    started_at: datetime | None
    completed_at: datetime | None
    labels: tuple[str, ...]
    steps: tuple[StepRecord, ...]


def _text(value: Any, limit: int) -> str:
    return str(value or "")[:limit]


def _optional_text(value: Any, limit: int) -> str | None:
    return None if value is None else str(value)[:limit]


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _sha(value: Any) -> str:
    sha = str(value or "")
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise GitHubError("upstream_error", "GitHub sent an unexpected commit id.")
    return sha


def run_record(data: dict[str, Any]) -> RunRecord:
    created = parse_time(data.get("created_at"))
    if created is None:
        raise GitHubError("upstream_error", "GitHub sent a run without a creation time.")
    repository = data.get("repository") or {}
    return RunRecord(
        run_id=int(data["id"]),
        run_attempt=max(1, int(data.get("run_attempt") or 1)),
        run_number=int(data.get("run_number") or 0),
        workflow_id=int(data.get("workflow_id") or 0),
        workflow_path=_text(data.get("path"), 300),
        workflow_name=_text(data.get("name"), 300),
        event=_text(data.get("event"), 50),
        head_branch=_optional_text(data.get("head_branch"), 300),
        head_sha=_sha(data.get("head_sha")),
        status=_text(data.get("status"), 32),
        conclusion=_optional_text(data.get("conclusion"), 32),
        created_at=created,
        run_started_at=parse_time(data.get("run_started_at")),
        updated_at=parse_time(data.get("updated_at")),
        private=bool(repository.get("private", False)),
    )


def job_record(data: dict[str, Any]) -> JobRecord:
    steps = tuple(
        StepRecord(
            number=int(step.get("number") or 0),
            name=_text(step.get("name"), 200),
            conclusion=_optional_text(step.get("conclusion"), 32),
            started_at=_optional_text(step.get("started_at"), 40),
            completed_at=_optional_text(step.get("completed_at"), 40),
        )
        for step in (data.get("steps") or [])[:MAX_STEPS]
        if isinstance(step, dict)
    )
    labels = tuple(_text(label, 100) for label in (data.get("labels") or [])[:20])
    return JobRecord(
        job_id=int(data["id"]),
        run_id=int(data.get("run_id") or 0),
        run_attempt=max(1, int(data.get("run_attempt") or 1)),
        name=_text(data.get("name"), 300),
        status=_text(data.get("status"), 32),
        conclusion=_optional_text(data.get("conclusion"), 32),
        started_at=parse_time(data.get("started_at")),
        completed_at=parse_time(data.get("completed_at")),
        labels=labels,
        steps=steps,
    )


class HistoryReader:
    """The GitHub endpoints history needs, each costing one request from the budget."""

    def __init__(self, client: GitHubClient, budget: RequestBudget) -> None:
        self.client = client
        self.budget = budget
        # Records GitHub sent that could not be read (a run without an id or a creation time):
        # skipped and counted, so one bad record never stops a sync.
        self.malformed = 0
        self.listed = 0  # size of the last run page, malformed records included

    def _parsed(self, items: list[Any], parse: Any) -> list[Any]:
        found = []
        for item in items:
            try:
                if not isinstance(item, dict):
                    raise TypeError(type(item).__name__)
                found.append(parse(item))
            except (KeyError, TypeError, ValueError, GitHubError):
                self.malformed += 1
        return found

    def _get(self, path: str, params: dict[str, str | int] | None, what: str) -> Any:
        self.budget.spend()
        return self.client.get_json(path, params, what=what)

    def repository(self, owner: str, repo: str) -> RepositoryMeta:
        check_name(owner, repo)
        data = self._get(f"/repos/{owner}/{repo}", None, f"repository {owner}/{repo}")
        if not isinstance(data, dict):
            raise GitHubError("upstream_error", "GitHub sent an unexpected repository.")
        return RepositoryMeta(
            owner=owner,
            repo=repo,
            default_branch=_optional_text(data.get("default_branch"), 300),
            private=bool(data.get("private", True)),
        )

    def runs_page(
        self, owner: str, repo: str, *, created: str, page: int
    ) -> tuple[list[RunRecord], int]:
        """One page of the repository's runs created in ``created`` (GitHub's range syntax),
        newest first, and GitHub's total count for the range."""
        check_name(owner, repo)
        data = self._get(
            f"/repos/{owner}/{repo}/actions/runs",
            {
                "created": created,
                "per_page": PER_PAGE,
                "page": page,
                "exclude_pull_requests": "true",
            },
            f"workflow runs of {owner}/{repo}",
        )
        if not isinstance(data, dict):
            raise GitHubError("upstream_error", "GitHub sent an unexpected run listing.")
        items = data.get("workflow_runs") or []
        if not isinstance(items, list):
            raise GitHubError("upstream_error", "GitHub sent an unexpected run listing.")
        self.listed = len(items)  # the page's size, malformed records included (pagination)
        return self._parsed(items, run_record), int(data.get("total_count") or 0)

    def run(self, owner: str, repo: str, run_id: int, attempt: int | None = None) -> RunRecord:
        check_name(owner, repo)
        path = f"/repos/{owner}/{repo}/actions/runs/{int(run_id)}"
        if attempt is not None:
            path += f"/attempts/{int(attempt)}"
        data = self._get(path, None, f"run {run_id} of {owner}/{repo}")
        if not isinstance(data, dict):
            raise GitHubError("upstream_error", "GitHub sent an unexpected run description.")
        return run_record(data)

    def jobs(self, owner: str, repo: str, run_id: int, attempt: int) -> list[JobRecord]:
        """Every job of one run attempt (at most ``MAX_JOB_PAGES`` pages)."""
        check_name(owner, repo)
        path = f"/repos/{owner}/{repo}/actions/runs/{int(run_id)}/attempts/{int(attempt)}/jobs"
        found: list[JobRecord] = []
        for page in range(1, MAX_JOB_PAGES + 1):
            data = self._get(path, {"per_page": PER_PAGE, "page": page}, f"jobs of run {run_id}")
            items = data.get("jobs") or [] if isinstance(data, dict) else []
            if not isinstance(items, list):
                items = []
            found += self._parsed(items, job_record)
            if len(items) < PER_PAGE:
                break
        return found
