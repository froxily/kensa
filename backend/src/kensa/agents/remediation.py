"""Remediation proposals (M3). Read-only by construction: nothing in Kensa applies them.

Two kinds of proposal:
* Recommended fixes (text) from the accepted diagnosis, with the category's risks and
  validation steps. Rules-only runs label them "template".
* Minimal file edits suggested by the model. An edit names a repository evidence block, an exact
  ``find`` text and a ``replace`` text. Kensa checks it against the full file (the text must
  occur exactly once; no secrets, no instruction-like text, a safe relative path), then checks
  the edited file's structure: it must still parse (YAML, JSON, TOML, Python; parsed only, never
  executed), YAML keys that existed must still exist, every workflow step must still have
  ``run`` or ``uses``, a changed ``run:`` script must keep its shell constructs balanced, and no
  added script line may print a variable that holds a secret. Only then does Kensa compute the
  unified diff itself. An edit that fails any check is dropped and counted.
"""

import ast
import difflib
import json
import re
import tomllib
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import yaml

from kensa.agents.evidence import EvidenceItem
from kensa.agents.schemas import EDIT_TEXT_MAX, EditDraft
from kensa.agents.verifier import RISKY_FIX_PATTERNS
from kensa.analysis.categories import Category
from kensa.analysis.indicators import is_instruction_like
from kensa.ingestion.redaction import redact

REPOSITORY_SOURCES = frozenset({"workflow_yaml", "code", "doc"})
MAX_PROPOSALS = 6
MIN_FIND_CHARS = 3
_UNSAFE_PATH = re.compile(r"(^|[\\/])\.\.([\\/]|$)|^[\\/]|^[A-Za-z]:")

CATEGORY_RISKS: dict[Category, list[str]] = {
    "missing_env_var": [
        "A secret must be stored as a repository or environment secret, never written into "
        "the workflow file or the repository.",
    ],
    "dependency_build": [
        "Changing versions or the lockfile can change behaviour elsewhere; review the "
        "lockfile diff.",
    ],
    "github_permissions": [
        "Broader token permissions widen what a compromised step could do; grant only what "
        "this job needs.",
    ],
    "db_connectivity": [
        "Connection settings differ between service containers and the runner host; check "
        "both before changing them.",
    ],
    "docker": ["A different image tag or base image can change the build environment."],
    "workflow_path": ["Moving paths can break other jobs or local scripts that use them."],
    "test_regression": [
        "Changing the test instead of the code hides a real regression unless the behaviour "
        "change was intended.",
    ],
    "oom_timeout": [
        "Raising limits hides the underlying growth in memory, disk or time; confirm the "
        "workload needs it.",
    ],
    "unknown": [],
}

CATEGORY_VALIDATION: dict[Category, list[str]] = {
    "missing_env_var": [
        "Re-run the failed job and confirm the step that read the variable passes.",
        "Confirm the variable is defined for this job without printing secret values.",
    ],
    "dependency_build": [
        "Reproduce the install or build locally with the same lockfile and tool versions.",
        "Re-run the failed job and confirm the install and build steps pass.",
    ],
    "github_permissions": [
        "Re-run the job and confirm the API call or push succeeds with the narrowed permissions.",
    ],
    "db_connectivity": [
        "Re-run the job and confirm the database service is healthy before the tests start.",
    ],
    "docker": ["Build or pull the image locally with the same tag, then re-run the job."],
    "workflow_path": ["Re-run the job and confirm the referenced path exists at this commit."],
    "test_regression": [
        "Run the failing test locally on this commit, then re-run the job.",
    ],
    "oom_timeout": [
        "Re-run the job and compare memory, disk and duration with the failed run.",
    ],
    "unknown": [],
}


@dataclass(frozen=True)
class Proposal:
    title: str
    action: str
    rationale: str
    origin: str  # "model" | "template"
    risks: tuple[str, ...]
    validation_steps: tuple[str, ...]
    flags: tuple[str, ...] = ()
    target_document_id: uuid.UUID | None = None
    target_path: str | None = None
    diff: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "action": self.action,
            "rationale": self.rationale,
            "origin": self.origin,
            "risks": list(self.risks),
            "validation_steps": list(self.validation_steps),
            "flags": list(self.flags),
            "target_document_id": (
                str(self.target_document_id) if self.target_document_id else None
            ),
            "target_path": self.target_path,
            "diff": self.diff,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Proposal":
        document_id = data.get("target_document_id")
        return cls(
            title=data["title"],
            action=data["action"],
            rationale=data["rationale"],
            origin=data["origin"],
            risks=tuple(data["risks"]),
            validation_steps=tuple(data["validation_steps"]),
            flags=tuple(data["flags"]),
            target_document_id=uuid.UUID(document_id) if document_id else None,
            target_path=data.get("target_path"),
            diff=data.get("diff"),
        )


def risk_flags(text: str) -> tuple[str, ...]:
    return tuple(label for label, pattern in RISKY_FIX_PATTERNS if pattern.search(text))


def _title(text: str) -> str:
    first = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]
    return first if len(first) <= 120 else first[:117].rstrip() + "..."


def fix_proposals(fixes: Sequence[str], category: Category, origin: str) -> list[Proposal]:
    return [
        Proposal(
            title=_title(fix),
            action=fix,
            rationale="",
            origin=origin,
            risks=tuple(CATEGORY_RISKS[category]),
            validation_steps=tuple(CATEGORY_VALIDATION[category]),
            flags=risk_flags(fix),
        )
        for fix in fixes
        if fix.strip()
    ]


@dataclass(frozen=True)
class RepositoryFile:
    document_id: uuid.UUID
    path: str
    content: str


KeyPath = tuple[object, ...]


def _identity(index: int, item: object) -> object:
    """A list item's identity that survives insertions: its name, id or uses, else its index."""
    if isinstance(item, dict):
        for key in ("name", "id", "uses"):
            if isinstance(item.get(key), str):
                return f"{key}={item[key]}"
    return index


def _key_paths(value: object, prefix: KeyPath = ()) -> set[KeyPath]:
    paths: set[KeyPath] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            path = (*prefix, key)
            paths.add(path)
            paths |= _key_paths(child, path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths |= _key_paths(child, (*prefix, _identity(index, child)))
    return paths


def _workflow_steps_runnable(workflow: object) -> bool:
    jobs = workflow.get("jobs") if isinstance(workflow, dict) else None
    if not isinstance(jobs, dict):
        return True
    for job in jobs.values():
        steps = job.get("steps") if isinstance(job, dict) else None
        for step in steps if isinstance(steps, list) else []:
            if not isinstance(step, dict) or ("run" in step) == ("uses" in step):
                return False
    return True


# Shell constructs whose openers and closers must stay balanced in an edited ``run:`` script.
_SHELL_PAIRS = (
    (re.compile(r"\[\["), re.compile(r"\]\]")),
    (re.compile(r"(?<![\w-])if(?![\w-])"), re.compile(r"(?<![\w-])fi(?![\w-])")),
    (re.compile(r"(?<![\w-])do(?![\w-])"), re.compile(r"(?<![\w-])done(?![\w-])")),
    (re.compile(r"(?<![\w-])case(?![\w-])"), re.compile(r"(?<![\w-])esac(?![\w-])")),
    (re.compile(r"\("), re.compile(r"\)")),
    (re.compile(r"\{"), re.compile(r"\}")),
)
_PRINTS = re.compile(r"(?<![\w-])(?:echo|printf)(?![\w-])")
_COMMANDS = re.compile(r";|&&|\|\||\|")


def _balance(script: str) -> tuple[int, ...]:
    counts = [len(o.findall(script)) - len(c.findall(script)) for o, c in _SHELL_PAIRS]
    quotes = len(re.findall(r'(?<!\\)"', script)) % 2
    dangling = int(script.rstrip().endswith("\\"))
    return (*counts, quotes, dangling)


def _env_secrets(*scopes: object) -> set[str]:
    names: set[str] = set()
    for scope in scopes:
        env = scope.get("env") if isinstance(scope, dict) else None
        if isinstance(env, dict):
            names |= {str(k) for k, v in env.items() if "secrets." in str(v)}
    return names


def _workflow_scripts(workflow: object) -> dict[KeyPath, tuple[str, set[str]]]:
    """Each step's ``run`` script with the env variables (any scope) that hold a secret."""
    scripts: dict[KeyPath, tuple[str, set[str]]] = {}
    jobs = workflow.get("jobs") if isinstance(workflow, dict) else None
    for job_id, job in (jobs or {}).items() if isinstance(jobs, dict) else []:
        steps = job.get("steps") if isinstance(job, dict) else None
        for index, step in enumerate(steps if isinstance(steps, list) else []):
            if isinstance(step, dict) and isinstance(step.get("run"), str):
                secrets = _env_secrets(workflow, job, step)
                scripts[(job_id, _identity(index, step))] = (step["run"], secrets)
    return scripts


def _script_problem(old: object, new: object) -> str | None:
    before = _workflow_scripts(old)
    for key, (script, secrets) in _workflow_scripts(new).items():
        previous = before.get(key, ("", set()))[0]
        if script == previous:
            continue
        old_lines = set(previous.split("\n"))
        added = [line for line in script.split("\n") if line not in old_lines]
        # A printing command's own arguments must not include a secret-backed variable; testing
        # it elsewhere on the line (``[ -z "$URL" ] && echo "empty"``) is fine.
        for line in added:
            for command in _COMMANDS.split(line):
                printed = _PRINTS.search(command)
                if printed and any(
                    re.search(rf"\${{?{re.escape(name)}\b", command[printed.end() :])
                    for name in secrets
                ):
                    return "exposes_secret"
        if _balance(script) != _balance(previous):
            return "breaks_shell"
    return None


def structure_problem(path: str, before: str, after: str) -> str | None:
    """Why an edit breaks the file's structure, or None. Files are parsed, never executed; a file
    that did not parse before the edit is not judged."""
    suffix = path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    old: object = None
    new: object = None
    try:
        if suffix in ("yml", "yaml"):
            old = yaml.safe_load(before)
        elif suffix == "json":
            json.loads(before)
        elif suffix == "toml":
            tomllib.loads(before)
        elif suffix == "py":
            ast.parse(before)
        else:
            return None
    except (yaml.YAMLError, ValueError, SyntaxError):
        return None
    try:
        if suffix in ("yml", "yaml"):
            new = yaml.safe_load(after)
        elif suffix == "json":
            json.loads(after)
        elif suffix == "toml":
            tomllib.loads(after)
        else:
            ast.parse(after)
    except (yaml.YAMLError, ValueError, SyntaxError):
        return "breaks_syntax"
    if suffix in ("yml", "yaml"):
        if _key_paths(old) - _key_paths(new):
            return "removes_existing_keys"
        workflow = path.startswith(".github/workflows/")
        if workflow and _workflow_steps_runnable(old) and not _workflow_steps_runnable(new):
            return "breaks_workflow"
        if workflow:
            return _script_problem(old, new)
    return None


def validate_edit(
    edit: EditDraft,
    evidence: Mapping[str, EvidenceItem],
    files: Mapping[uuid.UUID, RepositoryFile],
    *,
    risks: Sequence[str] = (),
    validation_steps: Sequence[str] = (),
) -> Proposal | str:
    """Returns the proposal, or the reason the edit was dropped."""
    item = evidence.get(edit.evidence_id.strip().upper())
    if item is None:
        return "unknown_evidence"
    if item.source_type not in REPOSITORY_SOURCES:
        return "not_a_repository_file"
    file = next((f for f in files.values() if f.path == item.document_name), None)
    if file is None:
        return "file_unavailable"
    if _UNSAFE_PATH.search(file.path):
        return "unsafe_path"
    content = file.content.replace("\r\n", "\n")
    find = edit.find.replace("\r\n", "\n")
    replace = edit.replace.replace("\r\n", "\n")
    if len(find.strip()) < MIN_FIND_CHARS:
        return "find_too_short"
    if len(edit.find) >= EDIT_TEXT_MAX or len(edit.replace) >= EDIT_TEXT_MAX:
        return "truncated"
    if content.count(find) != 1:
        return "find_not_unique" if content.count(find) > 1 else "find_not_in_file"
    if replace == find:
        return "no_change"
    if redact(replace).total > 0:
        return "contains_secret"
    if is_instruction_like(replace) or is_instruction_like(edit.explanation):
        return "instruction_like"
    updated = content.replace(find, replace, 1)
    problem = structure_problem(file.path, content, updated)
    if problem is not None:
        return problem
    diff = "\n".join(
        difflib.unified_diff(
            content.split("\n"),
            updated.split("\n"),
            fromfile=f"a/{file.path}",
            tofile=f"b/{file.path}",
            n=2,
            lineterm="",
        )
    )
    return Proposal(
        title=f"Edit {file.path}",
        action=edit.explanation.strip() or f"Change {file.path} as shown in the diff.",
        rationale=edit.explanation.strip(),
        origin="model",
        risks=tuple(risks),
        validation_steps=tuple(validation_steps),
        flags=risk_flags(replace),
        target_document_id=file.document_id,
        target_path=file.path,
        diff=diff,
    )


_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def apply_unified_diff(original: str, diff: str) -> str:
    """Rebuild the edited file from a stored unified diff (as ``validate_edit`` wrote it).
    Raises ``ValueError`` if the diff does not match the original."""
    old = original.replace("\r\n", "\n").split("\n")
    lines = diff.split("\n")
    result: list[str] = []
    cursor = 0
    index = 0
    while index < len(lines) and not lines[index].startswith("@@"):
        index += 1
    while index < len(lines):
        match = _HUNK.match(lines[index])
        if match is None:
            raise ValueError(f"unexpected diff line: {lines[index][:40]!r}")
        old_start, old_count = int(match.group(1)), int(match.group(2) or "1")
        start = old_start if old_count == 0 else old_start - 1
        if start < cursor:
            raise ValueError("overlapping hunks")
        result.extend(old[cursor:start])
        cursor = start
        index += 1
        while index < len(lines) and not lines[index].startswith("@@"):
            line = lines[index]
            tag, text = line[:1], line[1:]
            if tag in (" ", "-"):
                if cursor >= len(old) or old[cursor] != text:
                    raise ValueError("the diff does not match the original")
                cursor += 1
                if tag == " ":
                    result.append(text)
            elif tag == "+":
                result.append(text)
            elif line:
                raise ValueError(f"unexpected diff line: {line[:40]!r}")
            index += 1
    result.extend(old[cursor:])
    return "\n".join(result)


def recheck_proposal(path: str, original: str, diff: str) -> str | None:
    """Apply today's edit checks to a stored diff. Returns the reason it is unsafe, or None."""
    try:
        updated = apply_unified_diff(original, diff)
    except ValueError:
        return "diff_does_not_apply"
    added = "\n".join(
        line[1:] for line in diff.split("\n") if line.startswith("+") and not line.startswith("+++")
    )
    if redact(added).total > 0:
        return "contains_secret"
    if is_instruction_like(added):
        return "instruction_like"
    return structure_problem(path, original.replace("\r\n", "\n"), updated)
