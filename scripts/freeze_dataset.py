"""Validate an evaluation dataset against its quality gates and freeze it.

Gates for every version: every case loads (schema, splits, categories, kinds, exact evidence
ranges); each case has 3-6 repository files including a workflow; logs are not templated (no pair
of logs shares more than 25% of their timestamp-stripped, non-trivial lines).

* v1: logs have 50-160 lines; 20 dev and 20 test cases, 2 misleading and 2 insufficient each.
* v2 (M5.1): logs have 50-140 lines; every case matches its row in ``plan.csv`` (id prefix,
  split, category, kind); no credential-like strings; no line names the root cause or addresses
  a model; no log shares more than 25% of its lines with any v1 log either; 60 dev and 60 test.

Output names case ids and problem types only, never case content, so running the gates does not
expose held-out cases. On success, writes MANIFEST.sha256. Refuses to overwrite an existing
manifest unless --refreeze is given (a refreeze must be recorded in AUTHORING.md). ``--partial``
checks the cases written so far, without the count gates, and never freezes.

    uv run --directory backend --no-sync python ../scripts/freeze_dataset.py [--dataset v2]
"""

import argparse
import csv
import itertools
import re
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from kensa.analysis.indicators import is_instruction_like
from kensa.evaluation.dataset import (
    MANIFEST,
    Case,
    DatasetError,
    load_cases,
    manifest_lines,
    split_manifest_lines,
    split_manifest_name,
)

DATASETS = Path(__file__).resolve().parents[1] / "eval" / "datasets"
_STAMP = re.compile(r"^\S+Z\s?")
MAX_SHARED = 0.25
LOG_LINES = {"v1": (50, 160), "v2": (50, 140)}
# Lines GitHub's runner and the standard checkout/setup actions print in every real job. They are
# excluded from the similarity check by an explicit list, never by corpus frequency: a frequency
# filter would let a fully templated dataset (identical filler in every log) pass.
_RUNNER_BOILERPLATE = re.compile(
    r"^(?:Current runner version|Operating System|Runner Image|Image: |Runner name:|"
    r"GITHUB_TOKEN Permissions|Contents: |Metadata: |Secret source:|Prepare workflow directory|"
    r"Prepare all required actions|Preparing actions|Getting action download info|"
    r"Download action repository|Complete job name|shell: |Syncing repository|"
    r"Getting Git version info|git version|Temporarily overriding HOME|Adding repository directory|"
    r"Deleting the contents of|Initializing (?:the )?repository|Fetching the repository|"
    r"Checking out (?:the ref|commit)|Checkout complete|fetch-depth:|check-latest:|"
    r"(?:python|node|java|go|dotnet)-version:|Post job cleanup|Cleaning up orphan processes|"
    # `docker version` and BuildKit's fixed internal steps print the same lines in every job.
    r"docker version|(?:Client|Server): Docker Engine|API version:|Version: |"
    r"#\d+ \[internal\] load )"
)
# Added for v2 (M5.1) only; v1's gates stay exactly as they were when it was frozen. The
# hosted-runner banner, actions/checkout's post-job credential clean-up, BuildKit's header, the
# setup-go/java/node actions' fixed version lines, and masked values in a step's env.
_RUNNER_BOILERPLATE_V2 = re.compile(
    r"^(?:#0 building with |-{10,}$|Hosted Compute Agent|Runner Image Provisioner|"
    r"Removing credentials config|\[command\]/usr/bin/git |http\.https://github\.com/\.extraheader|"
    r"Added go to the path|Setup go version spec|Successfully set up |Resolved Java |"
    r"Setting Java |distribution: |Found in cache @|(?:node|npm|yarn|pnpm): v?\d|"
    r"[A-Z][A-Z0-9_]*: \*\*\*$|"
    # Action inputs GitHub echoes under `with:` ("ruby-version: 3.3"), and the setup-ruby,
    # setup-php and setup-beam actions' fixed lines.
    r"[a-z][a-z0-9-]*: \S+$|Entries added to PATH:|/opt/hostedtoolcache/|ruby \d|"
    r"==> Setup |\? PHP Installed|\? composer Added|(?:Elixir|OTP) [\d.]+ installed|"
    # Gradle's and `dotnet test`'s fixed lines, printed on every run of those tools.
    r"> Task :|Welcome to Gradle|Starting a Gradle Daemon|Gradle [\d.]+ is available|"
    r"\* What went wrong:|> Run with --|Execution failed for task|\d+ actionable tasks?:|"
    r"FAILURE: Build failed with an exception|BUILD (?:FAILED|SUCCESSFUL)|\d+ tests? completed|"
    r"Determining projects to restore|Starting test execution, please wait|"
    r"A total of \d+ test files? matched|VSTest version|Error Message:|Stack Trace:|"
    r"Using cached dotnet version|Test run for |"
    # Maven's banner and failure footer, pytest's section banners and header, pip's install lines.
    r"\[INFO\] (?:-{3,}|BUILD (?:FAILURE|SUCCESS)|Scanning for projects|  from pom\.xml|"
    r"Recompiling the module|Building )|\[ERROR\] (?:For more information about the errors|"
    r"Re-run Maven using|To see the full stack trace|-> \[Help)|Creating toolchains\.xml|"
    r"={5,}.*={5,}$|platform \w+ -- Python|collecting \.\.\.|rootdir: |cachedir: |plugins: |"
    r"Collecting |Installing collected packages|Successfully installed |Downloading |"
    r"Requirement already satisfied|pip install )"
)
_CREDENTIAL = re.compile(
    r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----|xox[abpr]-[A-Za-z0-9-]{10,}"
)
# Upper-case "NOTE:" only: tools print lower-case notes (rustc's "note: run with ...").
_GIVEAWAY = re.compile(r"(?i:\broot cause\b|\bhint:)|^\s*NOTE:")


def _content_lines(path: Path, *, v2: bool = False) -> set[str]:
    lines = {
        _STAMP.sub("", line).strip() for line in path.read_text(encoding="utf-8-sig").splitlines()
    }
    return {
        line
        for line in lines
        if len(line) > 12
        and not line.startswith("##[")
        and not _RUNNER_BOILERPLATE.match(line)
        and not (v2 and _RUNNER_BOILERPLATE_V2.match(line))
    }


def _templated(
    contents: dict[str, set[str]],
    pairs: Iterable[tuple[str, str]] | None = None,
    min_shared: int = 1,
) -> list[str]:
    """``min_shared`` (v2: 3) keeps one genuine shared error message between two short logs of
    the same category from counting as a template."""
    problems: list[str] = []
    for a, b in pairs if pairs is not None else itertools.combinations(contents, 2):
        shared = contents[a] & contents[b]
        smaller = min(len(contents[a]), len(contents[b])) or 1
        if len(shared) >= min_shared and len(shared) / smaller > MAX_SHARED:
            problems.append(f"{a} and {b} share {len(shared)}/{smaller} log lines (templated?)")
    return problems


def _v2_case_problems(case: Case, plan: dict[str, dict[str, str]]) -> list[str]:
    problems: list[str] = []
    prefix = case.id.split("-", 1)[0]
    row = plan.get(prefix)
    if row is None or not case.id.startswith(prefix + "-") or case.folder.name != case.id:
        problems.append(f"{case.id}: id or folder does not match a plan row")
    else:
        for field in ("split", "category", "kind"):
            if getattr(case, field) != row[field]:
                problems.append(f"{case.id}: {field} differs from plan.csv")
    files = [case.log_path, *(p for p in case.repo_path.rglob("*") if p.is_file())]
    for path in files:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        if _CREDENTIAL.search(text):
            problems.append(f"{case.id}: credential-like string in {path.name}")
        if path == case.log_path:
            for number, line in enumerate(text.splitlines(), start=1):
                if _GIVEAWAY.search(_STAMP.sub("", line)) or is_instruction_like(line):
                    problems.append(
                        f"{case.id}: log line {number} names the cause or addresses a model"
                    )
    return problems


def check(version: str, *, partial: bool = False) -> list[str]:
    root = DATASETS / version
    problems: list[str] = []
    try:
        cases = load_cases(root)
    except DatasetError as exc:
        return [str(exc)]
    low, high = LOG_LINES[version]
    plan: dict[str, dict[str, str]] = {}
    if version == "v2":
        with (root / "plan.csv").open(encoding="utf-8") as f:
            plan = {row["id_prefix"]: row for row in csv.DictReader(f)}
    for case in cases:
        log_lines = len(case.log_path.read_text(encoding="utf-8-sig").splitlines())
        if not low <= log_lines <= high:
            problems.append(f"{case.id}: log has {log_lines} lines (expected {low}-{high})")
        files = [p for p in case.repo_path.rglob("*") if p.is_file()]
        if not 3 <= len(files) <= 6:
            problems.append(f"{case.id}: {len(files)} repo files (expected 3-6)")
        if not any(".github/workflows" in p.as_posix() for p in files):
            problems.append(f"{case.id}: no workflow file")
        if version == "v2":
            problems += _v2_case_problems(case, plan)
    contents = {c.id: _content_lines(c.log_path, v2=version == "v2") for c in cases}
    problems += _templated(contents, min_shared=3 if version == "v2" else 1)
    if version == "v2":
        earlier = {
            f"v1/{c.id}": _content_lines(c.log_path, v2=True) for c in load_cases(DATASETS / "v1")
        }
        problems += _templated(
            {**contents, **earlier}, itertools.product(list(contents), list(earlier)), 3
        )
    if partial:
        return problems
    splits = Counter(c.split for c in cases)
    kinds = Counter((c.kind, c.split) for c in cases)
    if version == "v1":
        if splits != Counter({"dev": 20, "test": 20}):
            problems.append(f"split counts {dict(splits)} (expected 20/20)")
        for kind, expected in (("misleading", 2), ("insufficient", 2)):
            for split in ("dev", "test"):
                if kinds[(kind, split)] != expected:
                    problems.append(f"{kind}/{split}: {kinds[(kind, split)]} (expected {expected})")
    else:
        planned = Counter((row["kind"], row["split"]) for row in plan.values())
        if splits != Counter({"dev": 60, "test": 60}):
            problems.append(f"split counts {dict(splits)} (expected 60/60)")
        if kinds != planned:
            problems.append("kind counts per split differ from plan.csv")
    return problems


def freeze_split(root: Path, split: str, refreeze: bool) -> int:
    """Freeze one split's cases on their own (v2: dev before the test split exists)."""
    planned = Counter(
        r["split"] for r in csv.DictReader((root / "plan.csv").open(encoding="utf-8"))
    )
    have = len(load_cases(root, split))
    if have != planned[split]:
        print(f"FAIL {split}: {have} cases (expected {planned[split]})")
        return 1
    manifest = root / split_manifest_name(split)
    if manifest.exists() and not refreeze:
        print("Already frozen; use --refreeze (and document why) to change it.")
        return 1
    manifest.write_text("\n".join(split_manifest_lines(root, split)) + "\n", encoding="utf-8")
    print(f"Frozen {split}: {manifest}")
    return 0


def split_changes(root: Path) -> list[str]:
    """Splits frozen on their own must be unchanged when the whole set is frozen."""
    problems = []
    for manifest in sorted(root.glob("MANIFEST.*.sha256")):
        split = manifest.name.split(".")[1]
        recorded = manifest.read_text(encoding="utf-8").strip().splitlines()
        if recorded != split_manifest_lines(root, split):
            problems.append(f"the {split} split changed after it was frozen on its own")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and freeze an evaluation dataset.")
    parser.add_argument("--dataset", choices=sorted(LOG_LINES), default="v1")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--partial", action="store_true", help="cases so far; never freezes")
    parser.add_argument("--split", choices=["dev", "test"], help="freeze one split on its own")
    parser.add_argument("--refreeze", action="store_true")
    args = parser.parse_args()
    root = DATASETS / args.dataset
    problems = check(args.dataset, partial=args.partial or args.split is not None)
    if not args.partial and args.split is None:
        problems += split_changes(root)
    for problem in problems:
        print(f"FAIL {problem}")
    if problems:
        return 1
    print(f"PASS: {len(load_cases(root))} cases meet the quality gates")
    if args.check_only or args.partial:
        return 0
    if args.split is not None:
        return freeze_split(root, args.split, args.refreeze)
    manifest = root / MANIFEST
    if manifest.exists() and not args.refreeze:
        print("Already frozen; use --refreeze (and document why) to change it.")
        return 1
    manifest.write_text("\n".join(manifest_lines(root)) + "\n", encoding="utf-8")
    print(f"Frozen: {manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
