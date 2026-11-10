"""The facts change analysis works on, independent of where they come from (GitHub, or an
evaluation fixture). ``None`` always means *unknown*, never "the same" (the owner's correction
of 2026-11-09)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class JobFacts:
    name: str
    conclusion: str | None
    labels: tuple[str, ...] | None  # None: unknown
    runner_image: str | None = None
    runner_image_version: str | None = None
    job_id: int | None = None


@dataclass(frozen=True)
class RunFacts:
    run_id: int
    run_attempt: int
    workflow_path: str
    event: str
    head_branch: str | None
    head_sha: str
    created_at: datetime | None
    conclusion: str | None
    jobs: tuple[JobFacts, ...] | None  # None: not known

    def job(self, name: str) -> JobFacts | None:
        return next((j for j in self.jobs or () if j.name == name), None)


@dataclass(frozen=True)
class FileChange:
    """One file's change over the whole compared range, as GitHub's compare API reports it."""

    path: str
    status: str  # added | modified | removed | renamed
    previous_path: str | None
    additions: int
    deletions: int
    patch: str | None  # None when GitHub leaves it out (binary or very large)


@dataclass(frozen=True)
class Comparison:
    """GitHub's comparison of two commits. Commit messages are attacker-controlled text and are
    not kept; commit authors are personal data and are never read (D-052)."""

    status: str  # ahead | behind | identical | diverged | not_found
    merge_base: str | None
    commits: tuple[str, ...]  # SHAs, oldest first
    files: tuple[FileChange, ...]
    truncated: bool


class ChangeSource(Protocol):
    """Where the facts come from: GitHub (read-only, budgeted) or an evaluation fixture."""

    def candidates(self, failed: RunFacts, job_name: str) -> list[RunFacts]:
        """Earlier completed runs worth considering as the baseline, newest first."""
        ...

    def compare(self, base_sha: str, head_sha: str) -> Comparison: ...

    def workflow_blob(self, sha: str, path: str) -> str | None:
        """The workflow file's blob id at a commit, or None if unknown."""
        ...

    def baseline_log(self, run: RunFacts, job_name: str) -> list[str] | None:
        """The baseline job's log lines, if available (for its runner image)."""
        ...
