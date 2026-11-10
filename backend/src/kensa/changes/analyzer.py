"""Comparability and change ranking (v1.1, D-054). Pure functions: no database, no network.

**Comparability.** Each factor is recorded as ``same``, ``different``, ``unknown`` or (for the
workflow file) ``changed_in_range``. Unavailable information is uncertainty, never equivalence.
The verdict follows a fixed precedence:

1. ``no_baseline``: no earlier run succeeded.
2. ``incomparable``: successes exist, but none has the same workflow file path, event and
   branch, a successful job with the failed job's name, and the same (or unknown) runner
   labels.
3. Otherwise the newest such success is the baseline, and the comparison decides:
   * not found: ``history_unavailable``
   * behind: ``incomparable``
   * identical: ``identical``
   * diverged, any unknown factor, or another runner image version: ``partially_comparable``
   * otherwise: ``comparable``

**Ranking.** Changed files are scored by documented, deterministic signals. A suspect with a
strong signal is ``correlated``, otherwise ``weak``. Neither ever means "the cause".

| Signal | Weight |
|---|---|
| ``in_log``: the file's path appears in the failing log near a failure line | 3.0 |
| ``subject_in_diff``: a changed line names what failed (variable, module, test, image) | 3.0 |
| ``kind_matches_category``: the kind of file fits the failure's category | 1.5 |
| ``mentioned_in_log``: the path appears elsewhere in the log | 1.0 |
| ``size``: lines changed, up to | 0.5 |

Like GitHub's compare API, the analysis sees each file's change over the whole range,
not per commit, so it never ranks by recency.

Documentation-only files keep a fifth of their score. A runner image that changed between the
runs becomes a suspect of its own.
"""

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from kensa.analysis.indicators import FAILURE_MARKER
from kensa.changes.model import ChangeSource, Comparison, RunFacts
from kensa.github.importer import referenced_paths
from kensa.ingestion.normalize import strip_timestamp

RUNNER_IMAGE = "<runner-image>"
STRONG = 3.0
WEIGHTS = {
    "in_log": 3.0,
    "subject_in_diff": 3.0,
    "kind_matches_category": 1.5,
    "mentioned_in_log": 1.0,
    "size": 0.5,
    "runner_image_changed": 2.0,
    "image_fits_category": 1.0,
}
DOCS_FACTOR = 0.2
MAX_SUSPECTS = 5
MAX_HUNK_CHARS = 1500
IMAGE_SCAN_LINES = 120

CATEGORY_KINDS: dict[str, frozenset[str]] = {
    "missing_env_var": frozenset({"workflow", "env_declaration", "source", "build_config"}),
    "github_permissions": frozenset({"workflow"}),
    "db_connectivity": frozenset({"workflow", "build_config", "source", "env_declaration"}),
    "docker": frozenset({"build_config", "workflow"}),
    "workflow_path": frozenset({"workflow", "build_config"}),
    "dependency_build": frozenset({"dependency_manifest", "lockfile", "build_config", "source"}),
    "test_regression": frozenset({"source", "test"}),
    "oom_timeout": frozenset({"workflow", "test", "source", "build_config"}),
}
IMAGE_CATEGORIES = frozenset({"dependency_build", "docker", "oom_timeout", "workflow_path"})

_LOCKFILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "pipfile.lock",
    "uv.lock", "cargo.lock", "go.sum", "gemfile.lock", "composer.lock", "gradle.lockfile",
    "packages.lock.json", "mix.lock", "pubspec.lock", "bun.lockb", "flake.lock",
}  # fmt: skip
_MANIFESTS = {
    "package.json", "pyproject.toml", "setup.py", "setup.cfg", "pipfile", "cargo.toml",
    "go.mod", "gemfile", "composer.json", "pom.xml", "build.gradle", "build.gradle.kts",
    "settings.gradle", "settings.gradle.kts", "mix.exs", "package.swift", "global.json",
    ".nvmrc", ".node-version", ".python-version", ".tool-versions", "rust-toolchain",
    "rust-toolchain.toml", "gradle.properties", "build.sbt", "pubspec.yaml", "conanfile.txt",
    "vcpkg.json", "directory.packages.props",
}  # fmt: skip
_BUILD = {"makefile", "cmakelists.txt", ".dockerignore", "justfile", "taskfile.yml"}
_TEST_NAME = re.compile(
    r"(^test_.*|.*_test\.\w+$|.*\.test\.\w+$|.*\.spec\.\w+$|.*tests?\.\w+$|.*_spec\.rb$)", re.I
)
_IMAGE = re.compile(r"^\s*Image:\s*(\S+)")
_VERSION = re.compile(r"^\s*Version:\s*(\S+)")


def change_kind(path: str) -> str:
    posix = PurePosixPath(path)
    name = posix.name.lower()
    parts = [p.lower() for p in posix.parts]
    if path.startswith(".github/workflows/") and name.endswith((".yml", ".yaml")):
        return "workflow"
    if name in _LOCKFILES:
        return "lockfile"
    if name in _MANIFESTS or (name.startswith("requirements") and name.endswith((".txt", ".in"))):
        return "dependency_manifest"
    if name.endswith((".csproj", ".fsproj", ".vbproj")):
        return "dependency_manifest"
    if (
        name.startswith(("dockerfile", "docker-compose", "compose."))
        or name.endswith(".dockerfile")
        or name in _BUILD
    ):
        return "build_config"
    if name.startswith(".env") or name.endswith(".env"):
        return "env_declaration"
    if any(p in {"test", "tests", "__tests__", "spec", "specs"} for p in parts[:-1]):
        return "test"
    if _TEST_NAME.match(name):
        return "test"
    if name.endswith((".md", ".rst", ".adoc")) or "docs" in parts[:-1] or name == "license":
        return "docs"
    return "source"


def runner_image(lines: list[str]) -> tuple[str | None, str | None]:
    """The runner image and its version from a job log's set-up section, if it says."""
    image = version = None
    for raw in lines[:IMAGE_SCAN_LINES]:
        line = strip_timestamp(raw)
        if image is None and (m := _IMAGE.match(line)):
            image = m.group(1)
        elif image is not None and version is None and (m := _VERSION.match(line)):
            version = m.group(1)
            break
    return image, version


@dataclass(frozen=True)
class Factor:
    name: str  # workflow_file | event | branch | job | runner_labels | runner_image | history
    state: str  # same | different | unknown | changed_in_range
    detail: str


@dataclass
class Suspect:
    path: str
    change_kind: str
    score: float
    signals: dict[str, float]
    hunks: list[str]
    rank: int = 0

    @property
    def status(self) -> str:
        return "correlated" if self.score >= STRONG else "weak"


@dataclass
class ChangeAnalysis:
    comparability: str
    reasons: list[str]
    factors: list[Factor] = field(default_factory=list)
    baseline: RunFacts | None = None
    comparison: Comparison | None = None
    suspects: list[Suspect] = field(default_factory=list)

    @property
    def unverified(self) -> list[str]:
        """The factors that keep the runs from being fully comparable, in the evaluation
        set's vocabulary."""
        names: list[str] = []
        for f in self.factors:
            if f.name == "runner_image" and f.state == "unknown":
                names.append("runner_image_unknown")
            elif f.name == "runner_image" and f.state == "different":
                names.append("runner_image_changed")
            elif f.name == "runner_labels" and f.state == "unknown":
                names.append("runner_labels_unknown")
            elif f.name == "history" and f.state == "different":
                names.append("history_diverged")
            elif f.name == "baseline_log" and f.state == "unknown":
                names.append("baseline_log_unavailable")
            elif f.state == "unknown":
                names.append(f"{f.name}_unknown")
        return names


# -------------------------------------------------------------------------- baseline ---


def _structural_match(failed: RunFacts, candidate: RunFacts, job_name: str) -> list[str]:
    """Why a successful candidate cannot be the baseline (empty: it can)."""
    problems = []
    if candidate.workflow_path != failed.workflow_path:
        problems.append(f"another workflow file ({candidate.workflow_path})")
    if candidate.event != failed.event:
        problems.append(f"another event ({candidate.event})")
    if candidate.head_branch != failed.head_branch:
        problems.append(f"another branch ({candidate.head_branch})")
    job = candidate.job(job_name)
    if candidate.jobs is not None and (job is None or job.conclusion != "success"):
        problems.append(f'no successful job "{job_name}"')
    failed_job = failed.job(job_name)
    if (
        job is not None
        and failed_job is not None
        and job.labels is not None
        and failed_job.labels is not None
        and set(job.labels) != set(failed_job.labels)
    ):
        problems.append(f"other runner labels ({', '.join(job.labels)})")
    return problems


def choose_baseline(
    failed: RunFacts, candidates: list[RunFacts], job_name: str
) -> tuple[RunFacts | None, str | None, list[str]]:
    """The newest structurally matching success, or a verdict when there is none."""
    successes = [c for c in candidates if c.conclusion == "success"]
    if not successes:
        return None, "no_baseline", ["No earlier run of this workflow succeeded."]
    reasons: list[str] = []
    for candidate in successes:
        problems = _structural_match(failed, candidate, job_name)
        if not problems:
            return candidate, None, []
        reasons.append(f"Run {candidate.run_id}: " + "; ".join(problems) + ".")
    return None, "incomparable", reasons[:5]


# --------------------------------------------------------------------------- factors ---


def _factors(
    failed: RunFacts,
    baseline: RunFacts,
    job_name: str,
    comparison: Comparison,
    blobs: tuple[str | None, str | None],
    failed_image: tuple[str | None, str | None],
    baseline_log: list[str] | None,
) -> list[Factor]:
    factors = [
        Factor("event", "same", failed.event),
        Factor("branch", "same", failed.head_branch or ""),
    ]
    changed = {f.path for f in comparison.files} | {
        f.previous_path for f in comparison.files if f.previous_path
    }
    base_blob, failed_blob = blobs
    if base_blob is None or failed_blob is None:
        factors.append(
            Factor("workflow_file", "unknown", "The workflow file's version is unknown.")
        )
    elif base_blob == failed_blob:
        factors.append(Factor("workflow_file", "same", failed.workflow_path))
    elif failed.workflow_path in changed:
        factors.append(
            Factor("workflow_file", "changed_in_range", "The workflow file changed in between.")
        )
    else:
        factors.append(
            Factor("workflow_file", "different", "The workflow file differs outside the range.")
        )
    base_job, failed_job = baseline.job(job_name), failed.job(job_name)
    factors.append(Factor("job", "same" if base_job is not None else "unknown", job_name))
    if (
        base_job is None
        or base_job.labels is None
        or failed_job is None
        or failed_job.labels is None
    ):
        factors.append(Factor("runner_labels", "unknown", "The runner labels are unknown."))
    else:
        factors.append(Factor("runner_labels", "same", ", ".join(failed_job.labels)))
    factors.append(
        Factor(
            "baseline_log",
            "same" if baseline_log is not None else "unknown",
            "" if baseline_log is not None else "The baseline job's log is unavailable.",
        )
    )
    base_image: tuple[str | None, str | None] = (None, None)
    if baseline_log is not None:
        base_image = runner_image(baseline_log)
    if base_image == (None, None) and base_job is not None:
        base_image = (base_job.runner_image, base_job.runner_image_version)
    if failed_image == (None, None) and failed_job is not None:
        failed_image = (failed_job.runner_image, failed_job.runner_image_version)
    if None in base_image or None in failed_image:
        factors.append(Factor("runner_image", "unknown", "A runner image version is unknown."))
    elif base_image == failed_image:
        factors.append(Factor("runner_image", "same", f"{failed_image[0]} {failed_image[1]}"))
    else:
        factors.append(
            Factor(
                "runner_image",
                "different",
                f"{base_image[0]} {base_image[1]} -> {failed_image[0]} {failed_image[1]}",
            )
        )
    history_state = {"ahead": "same", "identical": "same", "diverged": "different"}.get(
        comparison.status, "unknown"
    )
    factors.append(Factor("history", history_state, comparison.status))
    return factors


# -------------------------------------------------------------------------- suspects ---


def _changed_lines(patch: str | None) -> list[str]:
    if not patch:
        return []
    return [
        line[1:]
        for line in patch.split("\n")
        if line[:1] in "+-" and line[:3] not in ("+++", "---")
    ]


def _hunks(patch: str | None) -> list[str]:
    if not patch:
        return []
    hunks: list[str] = []
    current: list[str] = []
    for line in patch.split("\n"):
        if line.startswith("@@") and current:
            hunks.append("\n".join(current))
            current = []
        current.append(line)
    if current:
        hunks.append("\n".join(current))
    return [h[:MAX_HUNK_CHARS] for h in hunks]


def _log_paths(log_lines: list[str]) -> tuple[set[str], set[str]]:
    """Paths near failure lines, and every path the log mentions."""
    text = "\n".join(log_lines)
    near = set(referenced_paths(text, 40)[:12])
    near_failure = {
        p
        for p in near
        if any(
            p in strip_timestamp(line) and FAILURE_MARKER.search(strip_timestamp(line))
            for line in log_lines
        )
    } | set(referenced_paths(text, 8))
    return near_failure, set(referenced_paths(text, 200))


def _in_log(path: str, paths: set[str], text: str) -> bool:
    if path in paths or any(p.endswith("/" + path) or path.endswith("/" + p) for p in paths):
        return True
    name = PurePosixPath(path).name
    return len(name) >= 8 and "." in name and name in text


def rank_suspects(
    comparison: Comparison,
    log_lines: list[str],
    subjects: list[str],
    category: str,
    image_factor: Factor | None = None,
) -> list[Suspect]:
    near, mentioned = _log_paths(log_lines)
    log_text = "\n".join(strip_timestamp(line) for line in log_lines)
    wanted = [s for s in dict.fromkeys(s.strip() for s in subjects) if len(s) >= 3]
    suspects: list[Suspect] = []
    for change in comparison.files:
        path = change.path
        kind = change_kind(path)
        signals: dict[str, float] = {}
        if _in_log(path, near, log_text):
            signals["in_log"] = WEIGHTS["in_log"]
        elif _in_log(path, mentioned, log_text):
            signals["mentioned_in_log"] = WEIGHTS["mentioned_in_log"]
        changed_text = "\n".join(_changed_lines(change.patch))
        if any(s.lower() in changed_text.lower() for s in wanted):
            signals["subject_in_diff"] = WEIGHTS["subject_in_diff"]
        if kind in CATEGORY_KINDS.get(category, frozenset()):
            signals["kind_matches_category"] = WEIGHTS["kind_matches_category"]
        size = change.additions + change.deletions
        signals["size"] = round(min(WEIGHTS["size"], size / 400), 3)
        score = sum(signals.values()) * (DOCS_FACTOR if kind == "docs" else 1.0)
        suspects.append(
            Suspect(
                path=path,
                change_kind=kind,
                score=round(score, 3),
                signals=signals,
                hunks=_hunks(change.patch),
            )
        )
    if image_factor is not None and image_factor.state == "different":
        signals = {"runner_image_changed": WEIGHTS["runner_image_changed"]}
        if category in IMAGE_CATEGORIES:
            signals["image_fits_category"] = WEIGHTS["image_fits_category"]
        suspects.append(
            Suspect(
                path=RUNNER_IMAGE,
                change_kind="runner_image",
                score=sum(signals.values()),
                signals=signals,
                hunks=[image_factor.detail],
            )
        )
    suspects.sort(key=lambda s: (-s.score, s.path))
    for rank, suspect in enumerate(suspects, 1):
        suspect.rank = rank
    return suspects[:MAX_SUSPECTS]


# ------------------------------------------------------------------------- analysis ---


def analyze(
    failed: RunFacts,
    job_name: str,
    log_lines: list[str],
    source: ChangeSource,
    *,
    subjects: list[str],
    category: str,
) -> ChangeAnalysis:
    """Choose the baseline, decide comparability factor by factor, and rank the changes."""
    candidates = [c for c in source.candidates(failed, job_name) if c.run_id != failed.run_id]
    baseline, verdict, reasons = choose_baseline(failed, candidates, job_name)
    if baseline is None:
        return ChangeAnalysis(comparability=verdict or "no_baseline", reasons=reasons)
    comparison = source.compare(baseline.head_sha, failed.head_sha)
    if comparison.status == "not_found":
        return ChangeAnalysis(
            "history_unavailable",
            ["GitHub cannot compare the commits (the baseline commit may be gone)."],
            baseline=baseline,
            comparison=comparison,
        )
    if comparison.status == "behind":
        return ChangeAnalysis(
            "incomparable",
            ["The failed commit is older than the baseline."],
            baseline=baseline,
            comparison=comparison,
        )
    blobs = (
        source.workflow_blob(baseline.head_sha, failed.workflow_path),
        source.workflow_blob(failed.head_sha, failed.workflow_path),
    )
    factors = _factors(
        failed,
        baseline,
        job_name,
        comparison,
        blobs,
        runner_image(log_lines),
        source.baseline_log(baseline, job_name),
    )
    image = next(f for f in factors if f.name == "runner_image")
    reasons = [f.detail for f in factors if f.state in ("unknown", "different") and f.detail]
    if comparison.truncated:
        reasons.append("GitHub listed only part of the changes (very large range).")
    if comparison.status == "identical":
        verdict = "identical"
        reasons.insert(0, "No code changed between the runs.")
    elif any(f.state in ("unknown", "different") for f in factors):
        verdict = "partially_comparable"
    else:
        verdict = "comparable"
    suspects = rank_suspects(comparison, log_lines, subjects, category, image)
    return ChangeAnalysis(verdict, reasons, factors, baseline, comparison, suspects)
