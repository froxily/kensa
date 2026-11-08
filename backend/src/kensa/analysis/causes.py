"""Cause-level evidence (M5.1, DECISIONS.md D-041).

A failed job usually reports a *symptom*: a failing test summary, a Docker build wrapper
("failed to solve"), an exit code. Sometimes the log also *states the underlying cause*: a
variable that must be set, a permission that was refused, a database that refused the
connection, memory that ran out. This module finds those statements, deterministically, over the
whole log.

Two uses:
* the rule classifier lets a stated environmental cause outrank the symptom lines that report
  it (a test that fails because a variable is missing is a missing variable, not a regression);
* the verifier marks a diagnosis "corroborated" only when the log states a cause of the claimed
  kind, a cited line shows it, and the log states no competing cause.

Text that a test asserts on is data under test, not the job's environment: a line such as
``expected "API_URL must be set", got nil`` is never read as a missing variable.

The patterns describe how tools commonly phrase these causes; they are written from the category
definitions, not from evaluation cases. A finding is evidence, not proof.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from kensa.analysis.categories import Category
from kensa.ingestion.normalize import strip_timestamp


def _r(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


# A variable name is upper case (case-sensitive): "Region is required" names no variable. The
# surrounding phrases are matched case-insensitively with scoped (?i:...) groups.
_VAR = r"['\"`]?\$?\{?([A-Z][A-Z0-9_]{2,})\}?['\"`]?"

# (rule id, pattern, regex group holding the subject such as a variable name, or 0 for none)
CAUSE_PATTERNS: dict[Category, tuple[tuple[str, re.Pattern[str], int], ...]] = {
    "missing_env_var": (
        (
            "env.named_missing",
            re.compile(
                r"(?i:environment variable|env(?:ironment)? var|\benv\b|secret|setting)s?\s+"
                + _VAR
                + r"\s+(?i:(?:is\s+|was\s+)?(?:not set|unset|missing|required|undefined"
                r"|not defined|empty|blank|not provided))"
            ),
            1,
        ),
        (
            "env.must_be_set",
            re.compile(
                _VAR + r"\s+(?i:must be (?:set|provided|defined)|is not set|is required|is unset"
                r"|is empty|is undefined|is not defined|was not provided|not provided"
                r"|environment variable (?:is )?(?:missing|not set|required))"
            ),
            1,
        ),
        (
            "env.missing_list",
            re.compile(
                r"(?i:missing (?:required )?(?:environment variables?|env(?:ironment)? vars?"
                r"|secrets?|settings?))[:\s]+['\"`]?([A-Z][A-Z0-9_]{2,})"
            ),
            1,
        ),
        ("env.keyerror", re.compile(r"KeyError: ['\"]([A-Z][A-Z0-9_]{2,})['\"]"), 1),
        (
            "env.unbound",
            re.compile(r"\b([A-Z][A-Z0-9_]{2,}): (?:unbound variable|parameter null or not set)"),
            1,
        ),
        ("env.placeholder", _r(r"Could not resolve placeholder '([\w.\-]+)'"), 1),
        ("env.action_input", _r(r"Input required and not supplied: ([\w\-]+)"), 1),
        (
            # Elixir's System.EnvError and similar "environment variable X ... not set" forms.
            "env.fetch",
            re.compile(
                r"(?i:environment variable) ['\"`]?([A-Z][A-Z0-9_]{2,})['\"`]?[^\n]{0,40}"
                r"(?i:\b(?:is not set|not set|is missing|is undefined|not defined|not present))"
            ),
            1,
        ),
        (
            # Rust's std::env::VarError::NotPresent, and "X not configured".
            "env.not_present",
            re.compile(r"\b([A-Z][A-Z0-9_]{2,})\b[^\n]{0,40}(?:NotPresent\b|(?i:not configured))"),
            1,
        ),
        (
            "env.process_env",
            re.compile(r"process\.env\.([A-Z][A-Z0-9_]{2,}) (?:is (?:undefined|not set|required))"),
            1,
        ),
    ),
    "github_permissions": (
        ("perm.integration", _r(r"Resource not accessible by (?:integration|personal access)"), 0),
        ("perm.push_denied", _r(r"Permission to \S+ denied to"), 0),
        ("perm.denied_code", _r(r"\bpermission_denied\b|\bwrite_package\b|\bread_package\b"), 0),
        (
            "perm.scope",
            _r(
                r"(?:requires?|missing|needs?) (?:the )?['\"`]?[a-z\-]+: ?write['\"`]? permission"
                r"|insufficient (?:permission|scope)s?|does not have (?:the )?(?:required )?"
                r"(?:permission|scope)|token (?:lacks|does not have)"
            ),
            0,
        ),
        ("perm.write_access", _r(r"write access to repository not granted"), 0),
        ("perm.must_have", _r(r"must have (?:admin|write|push|maintain) (?:rights|access)"), 0),
        (
            "perm.403",
            _r(r"(?:\b403\b[^\n]{0,40}(?:forbidden|denied|permission)|HttpError: 403|status 403)"),
            0,
        ),
    ),
    "db_connectivity": (
        ("db.auth", _r(r"password authentication failed for user"), 0),
        (
            "db.missing",
            _r(r"database \"[^\"]+\" does not exist|role \"[^\"]+\" does not exist"),
            0,
        ),
        ("db.mysql_denied", _r(r"Access denied for user '[^']*'@"), 0),
        ("db.mysql_unknown", _r(r"Unknown database '[^']+'"), 0),
        (
            "db.server",
            _r(
                r"could not connect to server|connection to server (?:at|on) .* failed"
                r"|Is the server running|Communications link failure|no pg_hba\.conf entry"
                r"|Can't connect to (?:local )?MySQL server|MongoServerSelectionError"
                r"|SQLSTATE\[HY000\] \[2002\]|redis\.exceptions\.ConnectionError"
                r"|Error: Redis connection to"
            ),
            0,
        ),
        (
            "db.port_refused",
            _r(
                r"(?:ECONNREFUSED|connection refused|connect: connection refused)"
                r"[^\n]{0,80}:(5432|3306|6379|27017|1433|9042|11211)\b"
                r"|:(5432|3306|6379|27017|1433|9042|11211)\b[^\n]{0,80}"
                r"(?:ECONNREFUSED|connection refused)"
            ),
            0,
        ),
        (
            # A database or cache host name that does not resolve (a service container that is
            # not reachable under that name), in either word order.
            "db.host_unknown",
            _r(
                r"(?:getaddrinfo (?:ENOTFOUND|EAI_AGAIN)|could not translate host name"
                r"|Name or service not known|lookup|Temporary failure in name resolution)"
                r"[^\n]{0,60}\b(?:postgres\w*|mysql\w*|mariadb|redis|mongo\w*|db|database|cache)"
                r"\b[^\n]{0,80}(?:no such host|ENOTFOUND|EAI_AGAIN|not known|resolution)"
                r"|\b(?:postgres\w*|mysql\w*|mariadb|redis|mongo\w*|db|database|cache)\b[^\n]{0,30}"
                r"(?:getaddrinfo (?:ENOTFOUND|EAI_AGAIN)|could not translate host name)"
                r"|(?:getaddrinfo (?:ENOTFOUND|EAI_AGAIN)|could not translate host name)"
                r"[^\n]{0,60}\b(?:postgres\w*|mysql\w*|mariadb|redis|mongo\w*|db|database|cache)\b"
            ),
            0,
        ),
        (
            "db.redis",
            re.compile(r"-ERR (?:DB index|invalid DB index)|\bNOAUTH\b|\bWRONGPASS\b"),
            0,
        ),
    ),
    "docker": (
        (
            "docker.daemon",
            _r(
                r"Cannot connect to the Docker daemon|Is the docker daemon running"
                r"|Could not find a valid Docker environment|docker\.sock: connect:"
            ),
            0,
        ),
        (
            "docker.pull",
            _r(
                r"pull access denied for|manifest (?:for \S+ )?(?:not found|unknown)"
                r"|no matching manifest for|repository does not exist or may require"
            ),
            0,
        ),
        (
            "docker.build",
            _r(
                r"failed to compute cache key|COPY failed|unknown instruction"
                r"|invalid reference format|failed to (?:resolve|load) source metadata"
                r"|dockerfile parse error|failed to read dockerfile"
            ),
            0,
        ),
    ),
    "workflow_path": (
        ("path.requirements", _r(r"Could not open requirements file"), 0),
        (
            "path.action",
            _r(r"Can't find '(?:action\.ya?ml|Dockerfile)'|Unable to resolve action"),
            0,
        ),
        ("path.artifact", _r(r"No files were found with the provided path"), 0),
        ("path.msbuild", _r(r"MSB1009|Project file does not exist"), 0),
        ("path.working_dir", _r(r"working-directory[^\n]{0,60}(?:does not exist|not found)"), 0),
        (
            "path.no_such",
            _r(
                r"(?:\S*/\S+|\S+\.\w{1,6})['\"`:]*:? No such file or directory"
                r"|\[Errno 2\] No such file or directory|ENOENT: no such file"
            ),
            0,
        ),
        ("path.pathspec", _r(r"pathspec '[^']+' did not match"), 0),
        (
            "path.target",
            _r(r"No rule to make target|Don't know how to build task '[^']*[/.][^']*'"),
            0,
        ),
    ),
    "dependency_build": (
        ("dep.py_module", re.compile(r"ModuleNotFoundError: No module named"), 0),
        (
            "dep.resolution",
            _r(
                r"No matching distribution found|ResolutionImpossible|could not resolve dependency"
                r"|conflicting peer dependency|Could not resolve all (?:files|dependencies)"
                r"|npm (?:ERR!|error) code E(?:RESOLVE|TARGET|404|NOTARGET)"
                r"|ERR_PNPM_\w+|version solving failed|unsatisfiable"
            ),
            0,
        ),
        (
            "dep.lockfile",
            _r(
                r"lock ?file[^\n]{0,60}(?:out of date|not up to date|needs to be updated"
                r"|is not in sync)|frozen-lockfile|missing go\.sum entry"
                r"|go: updates to go\.mod needed"
                r"|Your bundle is locked|lock file's \S+ does not match"
            ),
            0,
        ),
        (
            "dep.compile",
            _r(
                r"error\[E\d{4}\]|error TS\d{4}:|cannot find symbol|undefined reference to"
                r"|error: could not compile|unresolved import|error CS\d{4}:|compilation failed"
                r"|Parse error: syntax error|syntax error, unexpected|\bSyntaxError: "
            ),
            0,
        ),
        (
            "dep.version",
            _r(
                r"requires (?:a different )?Python|requires-python|rust-version|\bMSRV\b"
                r"|requires (?:node|go|java|ruby) (?:version )?[>=~^]"
                r"|engine \"node\" is incompatible"
                r"|unsupported class file major version"
            ),
            0,
        ),
        ("dep.import", _r(r"ImportError: cannot import name|ImportError while importing"), 0),
    ),
    "oom_timeout": (
        ("oom.137", _r(r"exit code 137\b|exited with code 137|signal: killed|OOMKilled"), 0),
        (
            "oom.memory",
            _r(
                r"JavaScript heap out of memory|out of memory|Cannot allocate memory|ENOMEM"
                r"|java\.lang\.OutOfMemoryError|GC overhead limit|MemoryError\b"
                r"|Killed signal terminated program|OutOfMemory(?:Error|Exception)"
                r"|Allowed memory size of \d+ bytes exhausted"
            ),
            0,
        ),
        ("oom.disk", _r(r"No space left on device"), 0),
        (
            "oom.timeout",
            _r(
                r"has exceeded the maximum execution time|The operation was canceled"
                r"|timed out after|deadline exceeded|exceeded the timeout"
            ),
            0,
        ),
    ),
    "test_regression": (
        (
            "test.assertion",
            _r(
                r"\bexpected\b[^\n]{0,120}"
                r"\b(?:but (?:was|got|found|received)|got|received|actual)\b"
                r"|\bwant(?:ed)?\b[^\n]{0,80}\bgot\b|\bgot\b[^\n]{0,80}\bwant(?:ed)?\b"
                r"|^\s*(?:Expected|Received|Actual)(?: value)?:\s|AssertionError: assert\b"
                r"|assertion (?:failed|`?left == right`?)|Assert\.\w+\(\) Failure"
                r"|Failed asserting that|expected:<[^>]*> but was:<|Assertion with \S+ failed"
                r"|^\s*(?:left|right):\s"
            ),
            0,
        ),
    ),
}

# Categories whose cause can hide behind a test, build or script failure. ``test_regression``
# is the usual symptom, so it never counts as a competing environmental cause.
ENVIRONMENTAL: frozenset[Category] = frozenset(
    {
        "missing_env_var",
        "github_permissions",
        "db_connectivity",
        "docker",
        "workflow_path",
        "dependency_build",
        "oom_timeout",
    }
)

# A line a test asserts on: its wording describes the code under test, not the environment.
_ASSERTION_TEXT = _r(r"\b(?:expected|expect\(|assert\w*)")
# A double-quoted value on a line: a cause phrase inside it is a string under test or a message
# being compared, not the job's state ("missing environment variable: X" as an expected value).
_QUOTED = re.compile(r'"[^"\n]*"')
_PREFILTER = _r(
    r"set|missing|required|undefined|defined|empty|keyerror|unbound|placeholder|process\.env"
    r"|denied|permission|forbidden|403|granted|scope|access|authentication|exist|connect|refused"
    r"|server|unknown|getaddrinfo|translate|docker|manifest|copy|instruction|reference|dockerfile"
    r"|cache key|no such|enoent|requirements|action|msb|pathspec|working-directory|no module"
    r"|matching|resol|peer|err|lock|go\.sum|go\.mod|bundle|error|symbol|compile|requires|msrv"
    r"|incompatible|import|137|killed|memory|space|canceled|timed out|deadline|timeout|expected"
    r"|want|got|received|actual|assert|configured|notpresent|no rule|build task|syntax|-err"
    r"|noauth|wrongpass|lookup|no such host|name resolution|exhausted|outofmemory"
)
_GROUP_START = re.compile(r"^##\[group\]Run ")
_GROUP_END = re.compile(r"^##\[endgroup\]")
_ENV_HEADER = re.compile(r"^env:\s*$")
_ENV_EMPTY = re.compile(r"^\s{2,}([A-Z][A-Z0-9_]{2,}):\s*$")


@dataclass(frozen=True)
class CauseLine:
    line_number: int
    category: Category
    rule_id: str
    subject: str | None = None


@dataclass(frozen=True)
class CauseEvidence:
    lines: tuple[CauseLine, ...] = ()

    @property
    def categories(self) -> frozenset[Category]:
        return frozenset(c.category for c in self.lines)

    def for_category(self, category: str) -> tuple[CauseLine, ...]:
        return tuple(c for c in self.lines if c.category == category)

    def line_numbers(self, category: str) -> frozenset[int]:
        return frozenset(c.line_number for c in self.lines if c.category == category)

    def competing(self, category: str) -> frozenset[Category]:
        """Environmental causes stated in the log other than ``category``."""
        return frozenset(c for c in self.categories if c != category and c in ENVIRONMENTAL)


def _line_causes(number: int, line: str) -> Iterable[CauseLine]:
    if not _PREFILTER.search(line):
        return
    in_assertion = (
        _ASSERTION_TEXT.search(line) is not None
        or CAUSE_PATTERNS["test_regression"][0][1].search(line) is not None
    )
    quoted = [m.span() for m in _QUOTED.finditer(line)]
    for category, patterns in CAUSE_PATTERNS.items():
        if in_assertion and category != "test_regression":
            continue
        for rule_id, pattern, group in patterns:
            match = pattern.search(line)
            if match is None:
                continue
            inside = any(a <= match.start() and match.end() <= b for a, b in quoted)
            if category != "test_regression" and inside:
                continue  # a quoted value ("... must be set") is data, not a statement
            subject = None
            if group:
                subject = next((g for g in match.groups() if g), None)
            yield CauseLine(number, category, rule_id, subject)
            break  # one finding per category per line


def assess_causes(lines: list[str]) -> CauseEvidence:
    """Cause statements in a log (1-based line numbers), in line order."""
    found: list[CauseLine] = []
    in_step = in_env = False
    for number, raw in enumerate(lines, start=1):
        line = strip_timestamp(raw)
        if _GROUP_START.match(line):
            in_step, in_env = True, False
            continue
        if _GROUP_END.match(line):
            in_step = in_env = False
            continue
        if in_step and _ENV_HEADER.match(line):
            in_env = True
            continue
        if in_env:
            # GitHub prints each step's environment; a secret that is set shows as ***.
            empty = _ENV_EMPTY.match(line)
            if empty:
                found.append(CauseLine(number, "missing_env_var", "env.empty_in_step", empty[1]))
            continue
        found.extend(_line_causes(number, line))
    return CauseEvidence(tuple(found))


def causes_to_json(evidence: CauseEvidence) -> list[dict[str, object]]:
    return [
        {"line": c.line_number, "category": c.category, "rule": c.rule_id, "subject": c.subject}
        for c in evidence.lines
    ]


def causes_from_json(data: list[dict[str, object]]) -> CauseEvidence:
    return CauseEvidence(
        tuple(
            CauseLine(
                int(str(item["line"])),
                item["category"],  # type: ignore[arg-type]
                str(item["rule"]),
                None if item.get("subject") is None else str(item["subject"]),
            )
            for item in data
        )
    )
