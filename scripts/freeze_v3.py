"""Quality gates and freezing for the v3 evaluation sets (v1.1).

    cd backend
    uv run --no-sync python ../scripts/freeze_v3.py --dataset v3-change --check-only
    uv run --no-sync python ../scripts/freeze_v3.py --dataset v3-history --split dev

The gates print problems by case or sequence id and kind only, so running them on the held-out
split never shows its content. Freezing writes ``MANIFEST.<split>.sha256``; with both splits
frozen, ``MANIFEST.sha256`` covers the whole set.

v3-change gates:
- plan conformity: id prefix, split, comparability, category, culprit_kind
- required files, log lengths, valid evidence ranges
- the comparability label follows from the facts by the spec's precedence rule. This is a short
  re-statement of the specification, written independently of Kensa's analyser, so a fact the
  author wrote inconsistently is caught.
- culprit paths appear among the baseline comparison's files (or the runner image changed)
- no credential-like strings and no giveaway commentary; no templating within a split or
  between dev and test

v3-history gates:
- plan conformity (pattern tokens → clusters and relations), files, log lengths
- a recurrence is not a near copy of its earlier entry
- credentials, giveaways, templating across sequences
"""

import argparse
import csv
import itertools
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from freeze_dataset import (
    _CREDENTIAL,
    _GIVEAWAY,
    _RUNNER_BOILERPLATE,
    _RUNNER_BOILERPLATE_V2,
    _STAMP,
    MAX_SHARED,
)

from kensa.evaluation.dataset import DatasetError
from kensa.evaluation.v3 import (
    freeze_all,
    freeze_split,
    load_change_case,
    load_history_sequence,
    split_folders,
)

DATASETS = Path(__file__).resolve().parents[1] / "eval" / "datasets"
FAILED_LINES, BASELINE_LINES, HISTORY_LINES = (60, 220), (40, 160), (40, 130)
COPY_SHARE = 0.8
# v3 additions to the explicit boilerplate list (never frequency filtering, as in v1 and v2):
# lines actions/checkout, the runner banner and setup actions print in every job.
_RUNNER_BOILERPLATE_V3 = re.compile(
    r"^(?:/usr/bin/git version|Initialized empty Git repository|Removing HTTP extra header|"
    r"Ubuntu \d|Windows Server \d|macOS \d|Runner Image Provisioner|Included Software:|"
    r"Image Release:|Hosted Compute Agent|Azure Region:|Provisioner|Version: \d|"
    # GitHub's service-container set-up and tear-down, printed for every `services:` entry.
    r"/usr/bin/docker (?:pull|rm|start|create|network|inspect|ps|version|logs) |"
    r"\d+: Pulling from |Status: Downloaded newer image|Stop and remove container:|"
    r"\S+ service is healthy|/usr/bin/git log -1 --format|"
    # Maven Surefire's result summary and setup-java's install line.
    r"\[INFO\] Results:|\[ERROR\] Failures:|\[INFO\] Tests run:|\[ERROR\] Tests run:|"
    r"Installed distributions|"
    # Python's own frames above every `python -m` traceback.
    r"Traceback \(most recent call last\):|File \"<frozen runpy>\")"
)
_TEXT = (
    ".log", ".json", ".yml", ".yaml", ".py", ".ts", ".js", ".go", ".rs", ".java", ".rb",
    ".toml", ".txt", ".md", ".cfg", ".lock", ".kt", ".cs", ".php", ".ex", ".exs", ".swift",
)  # fmt: skip


def _plan(root: Path) -> dict[str, dict[str, str]]:
    with (root / "plan.csv").open(encoding="utf-8") as handle:
        return {row["id_prefix"]: row for row in csv.DictReader(handle)}


class NotUtf8Error(ValueError):
    pass


def _lines(path: Path) -> list[str]:
    try:
        return path.read_bytes().decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise NotUtf8Error(path.name) from exc


def _utf8_problems(folder: Path) -> list[str]:
    bad = []
    for path in sorted(folder.rglob("*")):
        if path.is_file() and path.suffix.lower() in _TEXT:
            try:
                path.read_bytes().decode("utf-8-sig")
            except UnicodeDecodeError:
                bad.append(f"not valid UTF-8: {path.relative_to(folder).as_posix()}")
    return bad


def _content(path: Path) -> set[str]:
    out = set()
    for raw in _lines(path):
        line = _STAMP.sub("", raw).strip()
        if (
            len(line) > 12
            and not line.startswith("##[")
            and not _RUNNER_BOILERPLATE.match(line)
            and not _RUNNER_BOILERPLATE_V2.match(line)
            and not _RUNNER_BOILERPLATE_V3.match(line)
        ):
            out.add(line)
    return out


def _text_problems(folder: Path) -> list[str]:
    problems = []
    for path in folder.rglob("*"):
        if path.is_file() and path.suffix.lower() in _TEXT:
            text = path.read_bytes().decode("utf-8-sig", errors="replace")
            if _CREDENTIAL.search(text):
                problems.append(f"credential-like string in {path.relative_to(folder)}")
            if path.suffix == ".log" and any(
                _GIVEAWAY.search(_STAMP.sub("", line)) for line in text.splitlines()
            ):
                problems.append(f"giveaway commentary in {path.relative_to(folder)}")
    return problems


def _templated(contents: dict[str, set[str]], pairs: list[tuple[str, str]]) -> list[str]:
    found = []
    for a, b in pairs:
        shared = contents[a] & contents[b]
        smaller = min(len(contents[a]), len(contents[b])) or 1
        if len(shared) >= 3 and len(shared) / smaller > MAX_SHARED:
            found.append(f"{a} and {b} share {len(shared)}/{smaller} log lines (templated?)")
    return found


# ----------------------------------------------------------------------------- v3-change ---


def _structural(failed: dict[str, Any], candidate: dict[str, Any]) -> bool:
    if candidate.get("conclusion") != "success":
        return False
    same = all(candidate.get(k) == failed.get(k) for k in ("workflow_path", "event", "head_branch"))
    job_name = failed.get("failed_job")
    jobs = {j.get("name"): j for j in candidate.get("jobs") or []}
    job = jobs.get(job_name)
    failed_job = {j.get("name"): j for j in failed.get("jobs") or []}.get(job_name, {})
    if job is None or job.get("conclusion") != "success":
        return False
    labels_ok = (
        job.get("labels") is None
        or failed_job.get("labels") is None
        or set(job["labels"]) == set(failed_job["labels"])
    )
    return same and labels_ok


def expected_comparability(folder: Path) -> tuple[str, dict[str, Any] | None]:
    """The spec's precedence rule applied to the case's facts."""
    runs = json.loads((folder / "runs.json").read_text(encoding="utf-8-sig"))
    history = json.loads((folder / "history.json").read_text(encoding="utf-8-sig"))
    failed, candidates = runs["failed"], runs.get("candidates") or []
    if not any(c.get("conclusion") == "success" for c in candidates):
        return "no_baseline", None
    baseline = next((c for c in candidates if _structural(failed, c)), None)
    if baseline is None:
        return "incomparable", None
    comparison = (history.get("comparisons") or {}).get(
        f"{baseline['head_sha']}...{failed['head_sha']}"
    )
    if not isinstance(comparison, dict) or comparison.get("error") or "status" not in comparison:
        return "history_unavailable", None
    status = comparison["status"]
    if status == "behind":
        return "incomparable", comparison
    if status == "identical":
        return "identical", comparison
    job = {j.get("name"): j for j in baseline.get("jobs") or []}.get(failed.get("failed_job"), {})
    fjob = {j.get("name"): j for j in failed.get("jobs") or []}.get(failed.get("failed_job"), {})
    unknown = (
        not (folder / "baseline.log").is_file()
        or job.get("labels") is None
        or fjob.get("labels") is None
        or job.get("runner_image_version") is None
        or fjob.get("runner_image_version") is None
    )
    changed_image = job.get("runner_image_version") != fjob.get("runner_image_version")
    if status == "diverged" or unknown or changed_image:
        return "partially_comparable", comparison
    return "comparable", comparison


def change_problems(root: Path, folder: Path, plan: dict[str, dict[str, str]]) -> list[str]:
    if not (folder / "case.json").is_file():
        return ["missing case.json (incomplete)"]
    if encoding := _utf8_problems(folder):
        return encoding
    try:
        case = load_change_case(folder)
    except (DatasetError, KeyError, ValueError, json.JSONDecodeError) as exc:
        return [f"invalid case.json ({type(exc).__name__})"]
    problems = []
    row = plan.get(case.id.split("-", 1)[0])
    if row is None or folder.name != case.id:
        problems.append("id does not match a plan row or its folder")
    else:
        for field in ("split", "comparability", "category", "culprit_kind"):
            if getattr(case, field) != row[field]:
                problems.append(f"{field} differs from the plan")
    for name in ("failed.log", "runs.json", "history.json"):
        if not (folder / name).is_file():
            problems.append(f"missing {name}")
    if not list((folder / "repo/.github/workflows").glob("*.y*ml")):
        problems.append("missing the workflow under repo/.github/workflows")
    if problems:
        return problems
    failed_lines = _lines(folder / "failed.log")
    if not FAILED_LINES[0] <= len(failed_lines) <= FAILED_LINES[1]:
        problems.append(f"failed.log has {len(failed_lines)} lines")
    if (folder / "baseline.log").is_file():
        n = len(_lines(folder / "baseline.log"))
        if not BASELINE_LINES[0] <= n <= BASELINE_LINES[1]:
            problems.append(f"baseline.log has {n} lines")
    for ref in case.relevant_evidence:
        relative = ref.path.removeprefix("repo/")  # the spec allowed both spellings
        target = folder / "failed.log" if ref.path == "log" else folder / "repo" / relative
        if not target.is_file():
            problems.append(f"evidence path {ref.path} does not exist")
        elif not 1 <= ref.start_line <= ref.end_line <= len(_lines(target)):
            problems.append(f"evidence range {ref.path}:{ref.start_line}-{ref.end_line} is invalid")
    try:
        verdict, comparison = expected_comparability(folder)
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        return [*problems, f"runs.json or history.json is malformed ({type(exc).__name__})"]
    if verdict != case.comparability:
        problems.append(f"facts give {verdict}, label says {case.comparability}")
    if case.comparability == "partially_comparable" and not case.unverified:
        problems.append("partially_comparable without unverified_factors")
    if case.comparability not in ("comparable", "partially_comparable") and case.culprit_paths:
        problems.append("culprit_paths must be empty for this comparability")
    if comparison is not None and case.culprit_paths and "<runner-image>" not in case.culprit_paths:
        changed = {
            f.get("path") for c in comparison.get("commits") or [] for f in c.get("files") or []
        }
        missing = [p for p in case.culprit_paths if p not in changed]
        if missing:
            problems.append("a culprit path is not among the compared changes")
    return problems + _text_problems(folder)


# ---------------------------------------------------------------------------- v3-history ---


def _pattern(tokens: str) -> list[tuple[str, str, str | None]]:
    """Plan tokens to (cluster, relation, resembles)."""
    seen: set[str] = set()
    out = []
    for token in tokens.split():
        cluster, _, resembles = token.partition("~")
        relation = "lookalike" if resembles else ("recurrence" if cluster in seen else "first")
        seen.add(cluster)
        out.append((cluster, relation, resembles or None))
    return out


def history_problems(root: Path, folder: Path, plan: dict[str, dict[str, str]]) -> list[str]:
    if not (folder / "sequence.json").is_file():
        return ["missing sequence.json (incomplete)"]
    if encoding := _utf8_problems(folder):
        return encoding
    try:
        sequence = load_history_sequence(folder)
    except (DatasetError, KeyError, ValueError, json.JSONDecodeError) as exc:
        return [f"invalid sequence.json ({type(exc).__name__})"]
    problems = []
    row = plan.get(sequence.id.split("-", 1)[0])
    if row is None or folder.name != sequence.id:
        return ["id does not match a plan row or its folder"]
    if sequence.split != row["split"]:
        problems.append("split differs from the plan")
    wanted = _pattern(row["pattern"])
    if len(sequence.entries) != len(wanted):
        problems.append(f"{len(sequence.entries)} entries, the plan has {len(wanted)}")
    for entry, (cluster, relation, _) in zip(sequence.entries, wanted, strict=False):
        if entry.cluster.split(":", 1)[1] != cluster or entry.relation != relation:
            problems.append(f"{entry.id}: cluster or relation differs from the plan")
        if not entry.path.is_file():
            problems.append(f"{entry.id}: missing {entry.file}")
            continue
        n = len(_lines(entry.path))
        if not HISTORY_LINES[0] <= n <= HISTORY_LINES[1]:
            problems.append(f"{entry.id}: {n} log lines")
    by_cluster: dict[str, list[Any]] = {}
    for entry in sequence.entries:
        if entry.path.is_file():
            by_cluster.setdefault(entry.cluster, []).append(entry)
    for entries in by_cluster.values():
        for a, b in itertools.combinations(entries, 2):
            ca, cb = _content(a.path), _content(b.path)
            share = len(ca & cb) / (min(len(ca), len(cb)) or 1)
            if share > COPY_SHARE:
                problems.append(f"{b.id} is a near copy of {a.id} ({share:.0%} shared lines)")
    return problems + _text_problems(folder)


# ---------------------------------------------------------------------------------- main ---


def check(dataset: str, splits: list[str]) -> tuple[list[str], dict[str, int]]:
    root = DATASETS / dataset
    plan = _plan(root)
    gate = change_problems if dataset == "v3-change" else history_problems
    problems: list[str] = []
    counts: dict[str, int] = {}
    logs: dict[str, set[str]] = {}
    split_of: dict[str, str] = {}
    for split in splits:
        folders = split_folders(root, split)
        counts[split] = len(folders)
        for folder in folders:
            problems += [f"{folder.name}: {p}" for p in gate(root, folder, plan)]
            for log in sorted(folder.glob("*.log")):
                if log.name != "baseline.log" and not _utf8_problems(folder):
                    key = f"{folder.name}/{log.name}"
                    logs[key], split_of[key] = _content(log), split
    keys = sorted(logs)
    pairs = [
        (a, b) for a, b in itertools.combinations(keys, 2) if a.split("/")[0] != b.split("/")[0]
    ]
    problems += _templated(logs, pairs)
    return problems, counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dataset", choices=["v3-change", "v3-history", "v4-history"], required=True
    )
    parser.add_argument("--split", choices=["dev", "test"])
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--all", action="store_true", help="freeze the whole set (both splits)")
    args = parser.parse_args()
    splits = [args.split] if args.split else ["dev", "test"]
    problems, counts = check(args.dataset, splits)
    print(f"{args.dataset}: " + ", ".join(f"{s} {n}" for s, n in counts.items()))
    for problem in problems:
        print(f"  {problem}")
    if problems:
        print(f"{len(problems)} problem(s); nothing frozen.")
        return 1
    print("All gates passed.")
    if args.check_only:
        return 0
    root = DATASETS / args.dataset
    if args.all:
        print(f"Frozen: {freeze_all(root)}")
    elif args.split:
        print(f"Frozen: {freeze_split(root, args.split)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
