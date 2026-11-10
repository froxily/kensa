"""Deterministic failure fingerprints (v1.1, D-053; version 3 for v1.1.0, D-057).

A fingerprint names *what failed*, so that the same failure happening again is recognised even
when timestamps, run numbers, line numbers, temporary paths, durations, commands and tool
versions differ, while failures that only look alike stay apart.

It is built only from rule-derived facts, never from model output (history cannot confirm
itself, D-051).

**Two kinds, and only one of them is ever a recurrence claim:**

* **Exact:** the failure is identified by a **subject** the log names, for its **family** of
  rules: the variable, module, package, test (with its assertion), image, file, database or
  permission. A fingerprint built without such a subject is exact only when its line still holds
  a distinctive identifier (a quoted name, a path, a dotted symbol) after masking. Two
  investigations with the same exact primary fingerprint are reported as the **same failure**.
* **Approximate:** everything else, for example the tool's last error line when no rule knows
  the tool. An approximate fingerprint is only used to find *similar* failures, and is never
  presented as a recurrence: two different causes can print the same generic line.

**Families:** rules that report the same kind of fact share a family, so a recurrence that one
run reports through one rule and the next run through another (a missing module reported by
``ModuleNotFoundError`` and then by an import error) still matches. The rule id is kept for
display only.

Secondary fingerprints come from other strong signatures and find *related* failures, never
recurrences. ``FINGERPRINT_VERSION`` changes whenever the algorithm does, so old and new
fingerprints never mix.
"""

import hashlib
import re
from dataclasses import dataclass
from typing import Literal

from kensa.analysis.causes import CauseEvidence, CauseLine
from kensa.analysis.indicators import FAILURE_MARKER
from kensa.analysis.signatures import SignatureMatch
from kensa.ingestion.normalize import strip_timestamp

FINGERPRINT_VERSION = 3  # 3: families, subjects per family, exact and approximate kinds
MAX_SECONDARY = 3
SECONDARY_MIN_WEIGHT = 2
TEMPLATE_CHARS = 240
SUBJECT_CHARS = 200
CONTEXT_LINES = 40
NEAR_LINES = 6  # lines after a failure line that may still name its subject
# Signatures that never name a failure by themselves (GitHub's own error annotation).
GENERIC_RULES = frozenset({"gha.error", "exit.code"})

Role = Literal["primary", "secondary"]
Kind = Literal["exact", "approximate"]

# Lines that summarise a failure without naming it.
_SUMMARY = re.compile(
    r"process completed with exit code|exited with (?:code|status)|could not compile|"
    r"build failed|compilation failed|failed with exit code|command failed|the operation was "
    r"canceled|tests? failed|test suite failed|error: process|make(?:\[\d+\])?: \*\*\*|"
    r"^\s*error: \d+ errors?|^npm (?:err!|error) (?:code|errno|a complete log)|"
    r"execution failed for task|^\s*(?:tests?|test suites?):\s+\d+ failed|compilation error|"
    r"see (?:the )?(?:log|output|above) for (?:more )?details|errors? occurred|"
    r"^\s*(?:\[error\]\s*)?(?:total time|finished at|build failure)|^>?\s*task :\S+ failed"
    r"|found \d+ errors? in \d+ files?|\b(?:one|two|three|\d+) errors? found|"
    r"following build commands failed|failed with errors|\[help \d+\]|"
    r"requirements are unsatisfiable|^target \S+ failed|^\s*\d+ (?:failing|failed)\b|"
    r"^error: (?:command|script|process|recipe)\b|re-run maven|for more information about the "
    r"errors|\*\* [\w ]+ failed \*\*",
    re.IGNORECASE,
)
# A compiler diagnostic: a source position followed by a message, in any language
# (gcc/clang, go, rustc, kotlinc's "e: file://...", tsc and msbuild's "file(12,5):").
_DIAGNOSTIC = re.compile(
    r"^(?:[ew]: )?(?:file://)?\S*?[\w-]+\.[A-Za-z]{1,6}(?::\d+){1,2}:?\s+\S"
    r"|^\S+\.[A-Za-z]{1,6}\(\d+,\d+\):\s+\S"
)
# Header lines whose detail follows them (npm prints its error code first).
_HEADER = re.compile(r"^npm (?:err!|error) (?:code|errno)\b", re.IGNORECASE)
_STEP = re.compile(r"^##\[group\]Run (.+)")
# Decoration that tools print in front of the same message (pytest's "E", annotations, levels).
_DECORATION = re.compile(
    r"^(?:##\[(?:error|warning)\]|\[(?:error|err|fatal)\]\s*|e\s{2,}|>\s+|(?:fatal|error)(?=:)"
    r"|npm err!\s*|::error::|\u27a4\s*yn\d{4}:\s*[\u2502\u00b7]?)\s*:?\s*",
    re.IGNORECASE,
)

# ------------------------------------------------------------------------------- families ---

FAMILIES: dict[str, str] = {
    **dict.fromkeys(
        (
            "env.missing",
            "env.not_set",
            "env.keyerror",
            "env.named_missing",
            "env.must_be_set",
            "env.missing_list",
            "env.unbound",
            "env.placeholder",
            "env.fetch",
            "env.not_present",
            "env.process_env",
        ),
        "env",
    ),
    "env.empty_in_step": "env_empty",  # set but empty (a secret a fork cannot read): another fix
    "env.action_input": "action_input",
    **dict.fromkeys(("py.module", "dep.py_module", "node.module"), "module"),
    "dep.import": "import",
    **dict.fromkeys(("pip.no_dist", "composer.unresolvable"), "package"),
    **dict.fromkeys(
        ("dep.resolution", "pip.impossible", "npm.peer", "gradle.resolve", "dep.version"),
        "resolution",
    ),
    "dep.lockfile": "lockfile",
    **dict.fromkeys(("dep.compile", "ts.error", "rust.compile"), "compile"),
    **dict.fromkeys(
        (
            "pytest.failed",
            "pytest.summary",
            "jest.summary",
            "go.fail",
            "junit.fail",
            "test.assertion",
            "assertion",
        ),
        "test",
    ),
    "docker.pull": "image",
    **dict.fromkeys(("docker.build", "docker.solve"), "docker_build"),
    **dict.fromkeys(
        (
            "path.no_such",
            "path.enoent",
            "path.requirements",
            "path.action",
            "path.pathspec",
            "path.target",
            "path.working_dir",
            "path.msbuild",
        ),
        "path",
    ),
    **dict.fromkeys(("db.auth", "db.mysql_denied"), "db_auth"),
    **dict.fromkeys(("db.missing", "db.mysql_unknown"), "db_missing"),
    **dict.fromkeys(("db.server", "db.port_refused", "net.refused", "db.host_unknown"), "db_reach"),
    **dict.fromkeys(
        (
            "perm.integration",
            "perm.push_denied",
            "perm.denied_code",
            "perm.scope",
            "perm.write_access",
            "perm.must_have",
            "perm.403",
            "gh.integration",
            "gh.push_denied",
            "gh.bad_credentials",
            "http.403",
        ),
        "permission",
    ),
    **dict.fromkeys(("oom.137", "oom.heap", "oom.memory"), "memory"),
    **dict.fromkeys(("oom.disk", "disk.full"), "disk"),
    **dict.fromkeys(("oom.timeout", "timeout.job"), "timeout"),
}


def family_of(rule_id: str) -> str:
    return FAMILIES.get(rule_id, rule_id)


def _p(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


# What names the failure, per family: searched in the failure line and the lines just after it.
# Several groups are joined with ":" (an import of a name *from* a module).
_SUBJECTS: dict[str, tuple[re.Pattern[str], ...]] = {
    "module": (
        _p(r"No module named ['\"]?([\w.]+)"),
        _p(r"Cannot find (?:module|package) ['\"]([^'\"\s]+)['\"]"),
        _p(r"(?:Module not found|Can't resolve) ['\"]([^'\"\s]+)['\"]"),
        _p(r"cannot find package \"([^\"]+)\""),
        _p(r"no required module provides package ([\w./-]+)"),
    ),
    "import": (
        _p(r"cannot import name ['\"]?(\w+)['\"]? from ['\"]?([\w.]+)"),
        _p(r"ImportError while importing test module ['\"]?([^'\"\s]+)"),
    ),
    "package": (
        _p(r"No matching distribution found for ([\w.\-\[\]]+)"),
        _p(r"Root composer\.json requires ([^\s,]+)"),
    ),
    "resolution": (
        _p(r"Could not resolve dependency:\s*(?:peer\s+)?(@?[\w./-]+)@"),
        _p(r"Conflicting peer dependency:\s*(@?[\w./-]+)@"),
        _p(r"No matching version found for (@?[\w./-]+)@"),
        _p(r"Could not find ([\w.\-]+:[\w.\-]+)(?::[\w.\-]+)?"),
        _p(r"failed to select a version for (?:the requirement )?`?([\w-]+)"),
        _p(r"Because (?:every version of )?([\w.\-]+)(?:[=<>!~^]=?[\w.*]+)? (?:depends|requires)"),
        _p(r"conflict(?:ing)? (?:dependencies|requirements?) (?:for|on) ['\"]?([\w.\-]+)"),
        _p(r"(\S+) requires (?:a different )?Python"),
        _p(r"(?:missing|unmet) peer (@?[\w./-]+)@"),
        _p(r"So, because .*? depends on ([\w.\-]+)"),
    ),
    "compile": (
        _p(r"error\[(E\d{4})\]"),
        _p(r"error (TS\d{4})"),
        _p(r"error (CS\d{4})"),
        _p(r"cannot find symbol\s*:?\s*(?:symbol:\s*)?(?:\w+\s+)?(\w+)"),
        _p(r"undefined reference to [`'\"]?([\w:~]+)"),
        _p(r"undefined: (\w+)"),
        _p(r"^\s*symbol:\s+(?:variable|method|class|function)\s+(\w+)"),
        _p(r"error: (?:cannot find|use of undeclared|unresolved) [\w ]*?['`]([\w:]+)['`]"),
        _p(r"Unresolved reference:? '?(\w+)'?"),
    ),
    "test": (
        _p(r"^\s*FAIL\s+(\S+\.(?:test|spec)\.\w+)\s*>\s*(.+?)\s*$"),
        _p(r"\u203a\s*(\S+\.(?:spec|test)\.\w+):\d+:\d+\s*\u203a\s*(.+?)\s*$"),
        _p(r"^\s*[\u25cf\u2715\u00d7]\s+(.+?)\s*$"),
        _p(r"(\S+\.py::\S+)"),
        _p(r"--- FAIL: (\S+)"),
        _p(r"^\s*([\w.$]+)\s*>\s*(.+?)\s+FAILED\s*$"),
        _p(r"<<< (?:FAILURE|ERROR)!\s*-\s*in\s+([\w.$]+)"),
        _p(r"\[ERROR\]\s+([\w$]+(?:\.[\w$]+)+)\.(\w+):\d+"),
        _p(r"^\s*Failed (\S+) \["),
        _p(r"^\s*\d+\) test (.+?) \(([\w.]+)\)"),
        _p(r"^\s*\d+\) ([\w\\]+::\w+)"),
        _p(r"Test Case '-\[(\S+) (\S+)\]' failed"),
        _p(r"^\d+:\d+ \+\d+(?: ~\d+)?(?: -\d+)?: (.+?) \[E\]\s*$"),
        _p(r"^---- (\S+) stdout ----"),
        _p(r"^test (\S+) \.\.\. FAILED"),
        _p(r"rspec \./(\S+?\.rb)"),
        _p(r"^\s*\d+\) (.+?)\s*$"),
    ),
    "image": (
        _p(r"pull access denied for ([^\s,]+)"),
        _p(r"manifest for (\S+) not found"),
        _p(r"failed to resolve source metadata for ([^\s:]+(?::[^\s]+)?)"),
        _p(r"([\w.-]+(?:/[\w.-]+)+:[\w.-]+): not found"),
        _p(r"\bdocker (?:image )?pull (?:-\S+ )*([^\s;&|]+)"),
    ),
    "path": (
        _p(r"\[Errno 2\] No such file or directory: ['\"]([^'\"]+)['\"]"),
        _p(r"(\S*[/.]\S+?)['\"`:]*:? No such file or directory"),
        _p(r"ENOENT: no such file or directory, \w+ ['\"]([^'\"]+)['\"]"),
        _p(r"Could not open requirements file:.*?['\"]([^'\"]+)['\"]"),
        _p(r"pathspec '([^']+)' did not match"),
        _p(r"No rule to make target [`'\"]?([^'\"`,]+)"),
        _p(r"Don't know how to build task '([^']+)'"),
        _p(r"Can't find '([^']+)'"),
        _p(r"Unable to resolve action [`'\"]?([^'\"`,\s]+)"),
        _p(
            r"working-directory[^\n]{0,20}['\"`]?([\w./-]+)['\"`]?[^\n]{0,30}"
            r"(?:does not exist|not found)"
        ),
        _p(r"Project file does not exist\.?\s*(?:Switch: )?([\w./\\-]+)"),
    ),
    "db_reach": (
        _p(r"port\s+\"?(\d{2,5})\b"),
        _p(r"(?:ECONNREFUSED|refused)[^\n]*?:(\d{2,5})\b"),
        _p(r"[\w.-]+:(\d{2,5})[^\n]*(?:refused|unreachable|timed out)"),
    ),
    "memory": (
        _p(r"killed process \d+ \(([\w.-]+)\)"),
        _p(r"OutOfMemoryError: ([\w ]+)"),
        _p(r"(javascript heap) out of memory"),
        _p(r"(?:allocation of|memory allocation of) \d+ bytes failed"),
    ),
    "db_auth": (
        _p(r"password authentication failed for user ['\"]?([\w.-]+)"),
        _p(r"Access denied for user '([^']*)'@"),
    ),
    "db_missing": (
        _p(r"database ['\"]([^'\"]+)['\"] does not exist"),
        _p(r"role ['\"]([^'\"]+)['\"] does not exist"),
        _p(r"Unknown database '([^']+)'"),
    ),
    "permission": (
        _p(r"['\"`]?([a-z\-]+): ?write['\"`]? permission"),
        _p(r"Permission to (\S+) denied"),
        _p(r"\b(write_package|read_package)\b"),
    ),
    "docker_build": (
        _p(r"\"/([^\"]+)\": not found"),
        _p(r"COPY failed: (?:file not found in build context[^:]*: )?stat ([^\s:]+)"),
        _p(r"unknown instruction:? (\w+)"),
    ),
}
# Families whose own extracted value (a variable name, a test id) is the subject.
_RULE_SUBJECT_FAMILIES = frozenset({"env", "env_empty", "action_input", "test", "image"})
# Error codes are part of what failed, not who: kept in the template, never the subject alone.
_CODE_ONLY_RULES = frozenset({"npm.code", "ts.error", "exit.code"})

# Assertion lines: what makes one failure of a test different from another of the same test.
_ASSERTION = _p(
    r"\bassert(?:ion)?(?:error)?\b|\bexpected\b|\breceived\b|\bgot\b.*\bwant\b|\bwant\b.*\bgot\b"
    r"|\bto (?:be|equal|contain|have)\b|\bnot equal\b|\bmismatch\b"
)
_DISTINCT = re.compile(
    r"['\"`]([^'\"`\s<>]{3,80})['\"`]"  # a quoted name
    r"|(?<![\w<])[\w.-]*[a-z][\w.-]*/[\w./-]*[a-z][\w.-]*"  # a path
    r"|\b[a-z_][\w-]*\.(?:py|js|mjs|cjs|ts|tsx|jsx|go|rs|java|kt|kts|rb|php|cs|ex|exs|swift|c|cc"
    r"|cpp|h|hpp|ya?ml|json|toml|lock|tf|sh|gradle|xml|cfg|ini|dart|scala|clj)\b"  # a file name
    r"|\b[a-z_]\w*(?:\.\w+){2,}\b"  # a dotted symbol (com.acme.Thing, pkg.mod.func)
    r"|\b[a-z][\w-]*@[\w.^~<>=-]*\d",  # a versioned package (name@1.2)
    re.IGNORECASE,
)

# -------------------------------------------------------------------------------- masking ---

# Order matters: specific shapes are masked before the generic number mask.
_MASKS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"),
        "<ts>",
    ),
    (re.compile(r"\b\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\b"), "<ts>"),
    (
        re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I),
        "<uuid>",
    ),
    (re.compile(r"\bhttps?://([^/\s?#'\"]+)[^\s'\"]*"), r"<url:\1>"),
    (
        re.compile(
            r"(?:/home/runner/work|/Users/runner/work)/[^/\s]+/[^/\s]+/"
            r"|[A-Za-z]:[\\/]a[\\/][^\\/\s]+[\\/][^\\/\s]+[\\/]|/github/workspace/"
            r"|/__w/[^/\s]+/[^/\s]+/"
        ),
        "",
    ),
    (
        re.compile(
            r"(?:/tmp|/var/folders|/private/var|[A-Za-z]:\\Users\\[^\\\s]+\\AppData\\Local\\Temp)"
            r"[^\s'\":]*?([^/\\\s'\":]+)(?=[\s'\":]|$)"
        ),
        r"<tmp>/\1",
    ),
    (re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,64}\b", re.I), "<hex>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?\b"), "<ip>"),
    # A source position (file.go:41:7, file.cs(12,5)) moves with every edit, even in templates
    # that keep other numbers.
    (re.compile(r"(\.[A-Za-z]{1,6}):\d+(?::\d+)?\b"), r"\1:<line>"),
    (re.compile(r"(\.[A-Za-z]{1,6})\(\d+(?:,\d+)?\)"), r"\1(<line>)"),
    (
        re.compile(
            r"(?<![\w.])\d+(?:\.\d+)?\s?(?:ms|s|sec|secs|seconds|m|min|mins|minutes|h|hours)\b",
            re.I,
        ),
        "<dur>",
    ),
    (
        re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?\s?(?:[kmgt]i?b|bytes?|[kmg])(?![\w.])", re.I),
        "<size>",
    ),
    (re.compile(r"(['\"])[^'\"\n]{41,}\1"), "<str>"),
    (re.compile(r"#\d+\b"), "#<n>"),
    (re.compile(r"(?<=[a-z][_-])\d{3,}\b", re.I), "<n>"),
    (re.compile(r"(?<![\w.])\d+(?![\w.])"), "<n>"),
)
_SPACE = re.compile(r"\s+")
_NUMBER_MASK = _MASKS[-1][0]


@dataclass(frozen=True)
class Fingerprint:
    hash: str
    role: Role
    category: str
    rule_id: str
    subject: str
    template: str
    kind: Kind = "exact"


def mask(text: str, *, keep_numbers: bool = False) -> str:
    """The line with everything that varies between recurrences masked, lower-cased. With
    ``keep_numbers``, standalone numbers stay (a test's assertion values identify it)."""
    masked = strip_timestamp(text)
    for pattern, replacement in _MASKS:
        if keep_numbers and pattern is _NUMBER_MASK:
            continue
        masked = pattern.sub(replacement, masked)
    return _SPACE.sub(" ", masked).strip().lower()[:TEMPLATE_CHARS]


def _undecorated(text: str) -> str:
    """The message without the decoration tools print in front of it."""
    line = strip_timestamp(text).strip()
    for _ in range(3):
        stripped = _DECORATION.sub("", line, count=1).strip()
        if stripped == line:
            break
        line = stripped
    return line


def normalise_subject(subject: str | None) -> str:
    """A subject that masks to nothing but placeholders (a failure count, an exit code) names no
    failure, so it counts as no subject."""
    if not subject:
        return ""
    cleaned = re.sub(r"[\u2500-\u257f\u2190-\u21ff\u25a0-\u25ff]+", " ", subject)
    masked = mask(cleaned.strip("'\"`.,;: "))[:SUBJECT_CHARS]
    return "" if not re.sub(r"<\w+>|[\s.:#/,()-]", "", masked) else masked


def distinctive(template: str) -> bool:
    """Whether a masked line still names something specific: a quoted name, a path, a file, a
    dotted symbol or a versioned package (placeholders such as ``<n>`` do not count)."""
    return any(
        re.sub(r"<\w+(?::[^>]*)?>", "", m.group(0)).strip("'\"`/.:- ")
        for m in _DISTINCT.finditer(template)
    )


def _hash(*parts: str) -> str:
    key = "|".join((str(FINGERPRINT_VERSION), *parts))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _line(lines: list[str], number: int) -> str:
    return lines[number - 1] if 0 < number <= len(lines) else ""


_ECHO = re.compile(r"^(?:\[command\]|/usr/bin/|/bin/|shell: |##\[)")


def _substantive(text: str) -> bool:
    raw = strip_timestamp(text).strip()
    line = _undecorated(text)
    if len(line) < 12 or _ECHO.match(raw) or _SUMMARY.search(line):
        return False
    return bool(FAILURE_MARKER.search(line) or _DIAGNOSTIC.match(line))


def _names_failure(text: str) -> bool:
    """Whether a line names its failure by itself (not a summary, not a bare annotation)."""
    line = _undecorated(text)
    if len(line) < 12 or _ECHO.match(strip_timestamp(text).strip()) or _SUMMARY.search(line):
        return False
    return bool(FAILURE_MARKER.search(line) or _DIAGNOSTIC.match(line))


def _step_command(lines: list[str], number: int) -> str:
    for line in reversed([strip_timestamp(x).strip() for x in lines[: max(0, number - 1)]]):
        if match := _STEP.match(line):
            return match.group(1)
    return ""


_STEP_FAMILIES = frozenset({"memory", "disk", "timeout"})
_LOOK_BACK = frozenset({"test", "resolution", "compile"})
_GENERIC_STEPS = frozenset(
    {
        "",
        "test",
        "tests",
        "build",
        "check",
        "lint",
        "ci",
        "e2e",
        "unit",
        "integration",
        "verify",
        "install",
        "ci test",
        "run test",
        "run build",
    }
)
_WRAPPERS = frozenset(
    {
        "npm",
        "npx",
        "pnpm",
        "yarn",
        "bun",
        "run",
        "exec",
        "bundle",
        "python",
        "python3",
        "-m",
        "poetry",
        "uv",
        "sudo",
        "env",
        "time",
        "timeout",
        "bash",
        "sh",
        "make",
        "mix",
        "go",
        "cargo",
        "dotnet",
        "./gradlew",
        "gradle",
        "mvn",
        "./mvnw",
    }
)


def _step_words(lines: list[str], number: int) -> str:
    """The step's tool and target: the first words of its command that are not wrappers,
    options or paths (``npm run test:ci -- --runInBand`` gives ``test:ci``)."""
    words: list[str] = []
    for word in _step_command(lines, number).split():
        if word.startswith("-") or word in ("|", "&&", ";", ">"):
            break
        if word.lower() not in _WRAPPERS and "=" not in word and not word.startswith("$"):
            words.append(word)
    return " ".join(words[:2]).lower()


def _focus_line(lines: list[str], number: int) -> int:
    """The line that names the failure: the line itself; for a header, the first detail line
    after it; for a summary, the nearest earlier error line the tool printed."""
    if _HEADER.search(strip_timestamp(_line(lines, number)).strip()):
        for index in range(number, min(len(lines), number + NEAR_LINES)):
            text = strip_timestamp(lines[index]).strip()
            if not _HEADER.search(text) and _names_failure(text):
                return index + 1
    if _names_failure(_line(lines, number)):
        return number
    for index in range(number - 2, max(-1, number - 2 - CONTEXT_LINES), -1):
        if _substantive(lines[index]):
            return index + 1
    return number


def _extract(family: str, lines: list[str], number: int) -> str:
    """The subject a family's patterns find in the failure line or just after it."""
    patterns = _SUBJECTS.get(family, ())
    before = 15 if family in _LOOK_BACK else 0
    start = max(0, number - 1 - before)
    near = [strip_timestamp(x) for x in lines[number - 1 : number - 1 + NEAR_LINES]]
    earlier = [strip_timestamp(x) for x in reversed(lines[start : number - 1])]
    window = near + earlier
    if family == "image":
        window.append(_step_command(lines, number))  # `docker pull <image>` names the image
    for text in window:
        for pattern in patterns:
            if match := pattern.search(text):
                return ":".join(g for g in match.groups() if g)
    return ""


def _assertion(lines: list[str], number: int, causes: CauseEvidence) -> str:
    """The assertion a failing test reported near ``number``, masked with its values kept.
    pytest's echo of the source line (``>``) is skipped, and its ``E`` lines come first."""
    stated = {c.line_number for c in causes.lines if c.rule_id == "test.assertion"}
    candidates: list[tuple[tuple[int, int], str]] = []
    for index in range(max(0, number - 16), min(len(lines), number + 15)):
        raw = strip_timestamp(lines[index]).strip()
        if raw.startswith(">"):
            continue
        body = _undecorated(lines[index])
        if len(body) < 8 or not ((index + 1) in stated or _ASSERTION.search(body)):
            continue
        first = 0 if re.match(r"E\s", raw) else 1
        candidates.append(((first, abs(index + 1 - number)), body))
    return mask(min(candidates)[1], keep_numbers=True) if candidates else ""


def _build(
    lines: list[str],
    causes: CauseEvidence,
    category: str,
    rule_id: str,
    rule_subject: str | None,
    number: int,
    role: Role,
) -> Fingerprint:
    family = (
        "generic"
        if rule_id in GENERIC_RULES or rule_id == "generic.failure"
        else family_of(rule_id)
    )
    focus = _focus_line(lines, number)
    template = mask(_undecorated(_line(lines, focus)))
    subject = ""
    if family in _RULE_SUBJECT_FAMILIES and rule_id not in _CODE_ONLY_RULES:
        subject = normalise_subject(rule_subject)
    if not subject:
        extracted = _extract(family, lines, focus)
        subject = (
            f"port {extracted}"
            if family == "db_reach" and extracted
            else normalise_subject(extracted)
        )
    if family == "generic" and (test_name := normalise_subject(_extract("test", lines, focus))):
        family, subject = "test", test_name
    if family == "test":
        assertion = _assertion(lines, focus, causes) or template
        exact = bool(subject or distinctive(assertion)) and bool(assertion)
        key = _hash("test", subject, assertion)
        kind: Kind = "exact" if exact else "approximate"
        return Fingerprint(key, role, category, rule_id, subject, assertion or template, kind)
    if family == "compile":
        # Which error, where: the code or symbol, and the message with positions masked.
        exact = bool(subject) and distinctive(template)
        key = _hash("compile", subject, template)
        kind = "exact" if exact else "approximate"
        return Fingerprint(key, role, category, rule_id, subject, template, kind)
    if family in _STEP_FAMILIES:
        # What ran out of memory, disk or time: the process the log names, and the step.
        step = _step_words(lines, focus)
        if not subject and step in _GENERIC_STEPS:
            step = ""  # "test" or "build" alone would merge different jobs
        if subject or step:
            subject = normalise_subject(f"{subject} {step}".strip())
    if subject and family != "generic":
        return Fingerprint(_hash(family, subject), role, category, rule_id, subject, template)
    kind = (
        "exact" if distinctive(template) and _names_failure(_line(lines, focus)) else "approximate"
    )
    return Fingerprint(
        _hash(family, "", template), role, category, rule_id, subject, template, kind
    )


def _primary_cause(causes: CauseEvidence, category: str) -> CauseLine | None:
    matching = [c for c in causes.lines if c.category == category]
    candidates = matching or list(causes.lines)
    return candidates[0] if candidates else None


def _signature_subject(signature: SignatureMatch) -> str | None:
    return None if signature.value == signature.rule_id else signature.value


def _last_substantive(lines: list[str]) -> int | None:
    """The tool's own last error line (1-based), for logs with only generic signatures."""
    for index in range(len(lines) - 1, -1, -1):
        if _substantive(lines[index]):
            return index + 1
    return None


def fingerprints(
    lines: list[str],
    signatures: list[SignatureMatch],
    causes: CauseEvidence,
    rule_category: str,
) -> list[Fingerprint]:
    """The primary fingerprint (if the log has any signal) and up to ``MAX_SECONDARY`` others."""
    found: list[Fingerprint] = []
    ranked = sorted(signatures, key=lambda s: (-s.weight, s.line_number))
    specific = [s for s in ranked if s.rule_id not in GENERIC_RULES]
    cause = _primary_cause(causes, rule_category)
    of_category = next(
        (s for s in specific if s.category == rule_category and rule_category != "unknown"), None
    )
    if cause is not None and (cause.category == rule_category or of_category is None):
        found.append(
            _build(
                lines,
                causes,
                cause.category,
                cause.rule_id,
                cause.subject,
                cause.line_number,
                "primary",
            )
        )
    elif (strongest := of_category or (specific[0] if specific else None)) is not None:
        found.append(
            _build(
                lines,
                causes,
                strongest.category or rule_category,
                strongest.rule_id,
                _signature_subject(strongest),
                strongest.line_number,
                "primary",
            )
        )
    elif (number := _last_substantive(lines)) is not None:
        found.append(
            _build(lines, causes, rule_category, "generic.failure", None, number, "primary")
        )
    elif ranked:
        found.append(
            _build(
                lines,
                causes,
                rule_category,
                ranked[0].rule_id,
                None,
                ranked[0].line_number,
                "primary",
            )
        )
    seen = {f.hash for f in found}
    for signature in specific:
        if len(found) > MAX_SECONDARY or signature.weight < SECONDARY_MIN_WEIGHT:
            break
        candidate = _build(
            lines,
            causes,
            signature.category or rule_category,
            signature.rule_id,
            _signature_subject(signature),
            signature.line_number,
            "secondary",
        )
        if candidate.hash not in seen:
            seen.add(candidate.hash)
            found.append(candidate)
    return found
