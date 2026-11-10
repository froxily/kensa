"""Deterministic error-signature extraction (DECISIONS.md D-007).

Each rule maps a recognisable error line to a kind, a normalised value and a category hint with
a weight. Only lines that pass a cheap keyword prefilter are tested, so large logs stay fast.
"""

import re
from dataclasses import dataclass

from kensa.analysis.categories import Category
from kensa.ingestion.normalize import strip_timestamp

MAX_SIGNATURES = 200


@dataclass(frozen=True)
class SignatureRule:
    rule_id: str
    kind: str
    pattern: re.Pattern[str]
    category: Category | None
    weight: int
    value_group: int | None = None  # regex group holding the value; None = the rule id


@dataclass(frozen=True)
class SignatureMatch:
    line_number: int
    rule_id: str
    kind: str
    value: str
    category: Category | None
    weight: int
    excerpt: str


def _r(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


# Ordered roughly from most to least specific; several rules may match one line.
RULES: tuple[SignatureRule, ...] = (
    # missing_env_var
    SignatureRule(
        "env.missing",
        "missing_env",
        _r(
            r"missing (?:required )?(?:environment variable|env(?:ironment)? var|secret)s?[:\s]+['\"]?([A-Z_][A-Z0-9_]*)"
        ),
        "missing_env_var",
        3,
        1,
    ),
    SignatureRule(
        "env.not_set",
        "missing_env",
        _r(
            r"(?:environment variable|env var|secret) ['\"]?([A-Z_][A-Z0-9_]*)['\"]? (?:is )?(?:not set|not defined|undefined|missing|required|empty)"
        ),
        "missing_env_var",
        3,
        1,
    ),
    SignatureRule(
        "env.keyerror",
        "python_exception",
        re.compile(r"KeyError: '([A-Z_][A-Z0-9_]{2,})'"),
        "missing_env_var",
        2,
        1,
    ),
    # dependency_build
    SignatureRule(
        "npm.code",
        "npm_error_code",
        re.compile(r"npm (?:ERR!|error) code (E[A-Z0-9]+)"),
        "dependency_build",
        3,
        1,
    ),
    SignatureRule(
        "npm.peer",
        "npm_peer",
        _r(r"could not resolve dependency|conflicting peer dependency"),
        "dependency_build",
        2,
    ),
    SignatureRule(
        "py.module",
        "python_exception",
        re.compile(r"ModuleNotFoundError: No module named '([^']+)'"),
        "dependency_build",
        3,
        1,
    ),
    SignatureRule(
        "pip.no_dist",
        "pip_resolution",
        _r(r"No matching distribution found for (\S+)"),
        "dependency_build",
        3,
        1,
    ),
    SignatureRule(
        "pip.impossible",
        "pip_resolution",
        re.compile(r"ResolutionImpossible"),
        "dependency_build",
        3,
    ),
    SignatureRule(
        "node.module",
        "node_module",
        re.compile(r"Cannot find module '([^']+)'"),
        "dependency_build",
        2,
        1,
    ),
    SignatureRule(
        "ts.error", "compiler_error", re.compile(r"error (TS\d{4}):"), "dependency_build", 2, 1
    ),
    SignatureRule(
        "rust.compile", "compiler_error", _r(r"error: could not compile"), "dependency_build", 3
    ),
    SignatureRule(
        "composer.unresolvable",
        "composer_resolution",
        _r(
            r"Root composer\.json requires ([^\s,]+)[^\n]*?(?:does not match the constraint|"
            r"could not be found|does not satisfy)"
        ),
        "dependency_build",
        3,
        1,
    ),
    SignatureRule(
        "maven.goal",
        "build_tool",
        re.compile(r"\[ERROR\] Failed to execute goal"),
        "dependency_build",
        2,
    ),
    SignatureRule(
        "gradle.resolve",
        "build_tool",
        _r(r"Could not resolve all (?:files|dependencies)"),
        "dependency_build",
        3,
    ),
    # github_permissions
    SignatureRule(
        "gh.integration",
        "github_api",
        _r(r"Resource not accessible by integration"),
        "github_permissions",
        3,
    ),
    SignatureRule(
        "gh.push_denied", "git_remote", _r(r"Permission to \S+ denied"), "github_permissions", 3
    ),
    SignatureRule(
        "gh.bad_credentials", "github_api", _r(r"Bad credentials"), "github_permissions", 2
    ),
    SignatureRule(
        "http.403",
        "http_status",
        _r(r"(?:status(?: code)?|HTTP(?:/\d(?:\.\d)?)?)[:\s]+\"?(403)\b|\b(403) Forbidden"),
        "github_permissions",
        1,
    ),
    # db_connectivity
    SignatureRule(
        "db.auth", "db_error", _r(r"password authentication failed for user"), "db_connectivity", 3
    ),
    SignatureRule(
        "db.missing",
        "db_error",
        _r(r"database \"[^\"]+\" does not exist|role \"[^\"]+\" does not exist"),
        "db_connectivity",
        3,
    ),
    SignatureRule(
        "db.server",
        "db_error",
        _r(r"could not connect to server|connection to server at .* failed|Is the server running"),
        "db_connectivity",
        3,
    ),
    SignatureRule("db.jdbc", "db_error", _r(r"Communications link failure"), "db_connectivity", 3),
    SignatureRule(
        "db.port_refused",
        "connection_refused",
        re.compile(
            r"(?:ECONNREFUSED|Connection refused).*?:(5432|3306|27017|6379|1433)\b|:(5432|3306|27017|6379|1433)\b.*?(?:ECONNREFUSED|Connection refused)"
        ),
        "db_connectivity",
        3,
    ),
    SignatureRule(
        "net.refused",
        "connection_refused",
        _r(r"ECONNREFUSED|connection refused"),
        "db_connectivity",
        1,
    ),
    SignatureRule(
        "py.operational",
        "python_exception",
        re.compile(r"(\w+(?:\.\w+)*\.OperationalError)"),
        "db_connectivity",
        1,
        1,
    ),
    # docker
    SignatureRule(
        "docker.daemon",
        "docker",
        _r(r"Cannot connect to the Docker daemon|docker: Error response from daemon"),
        "docker",
        3,
    ),
    SignatureRule(
        "docker.solve", "docker", re.compile(r"(?:ERROR: )?failed to solve:"), "docker", 3
    ),
    SignatureRule(
        "docker.pull",
        "docker",
        _r(r"pull access denied for ([^\s,]+)|manifest for (\S+) not found|manifest unknown"),
        "docker",
        3,
        1,
    ),
    # workflow_path
    SignatureRule(
        "path.requirements",
        "missing_file",
        _r(r"Could not open requirements file"),
        "workflow_path",
        3,
    ),
    SignatureRule(
        "path.action",
        "missing_file",
        _r(r"Can't find '(action\.ya?ml|Dockerfile)'|Unable to resolve action"),
        "workflow_path",
        3,
    ),
    SignatureRule(
        "path.artifact",
        "missing_file",
        _r(r"No files were found with the provided path"),
        "workflow_path",
        3,
    ),
    SignatureRule(
        "path.enoent",
        "missing_file",
        re.compile(r"ENOENT: no such file or directory"),
        "workflow_path",
        2,
    ),
    SignatureRule(
        "path.no_such", "missing_file", _r(r"No such file or directory"), "workflow_path", 2
    ),
    # test_regression
    SignatureRule(
        "pytest.failed", "test_failure", re.compile(r"^FAILED (\S+::\S+)"), "test_regression", 3, 1
    ),
    SignatureRule(
        "pytest.summary",
        "test_failure",
        re.compile(r"=+ .*?\b(\d+) failed\b"),
        "test_regression",
        3,
        1,
    ),
    SignatureRule(
        "jest.summary",
        "test_failure",
        re.compile(r"Tests:\s+(\d+) failed"),
        "test_regression",
        3,
        1,
    ),
    SignatureRule(
        "go.fail", "test_failure", re.compile(r"^--- FAIL: (\S+)"), "test_regression", 3, 1
    ),
    SignatureRule(
        "junit.fail",
        "test_failure",
        re.compile(r"Tests run: \d+, Failures: [1-9]"),
        "test_regression",
        3,
    ),
    SignatureRule(
        "assertion", "test_failure", re.compile(r"\bAssertionError\b"), "test_regression", 2
    ),
    # oom_timeout
    SignatureRule("oom.137", "exit_code", _r(r"exit code 137\b"), "oom_timeout", 3),
    SignatureRule(
        "oom.heap",
        "oom",
        _r(r"JavaScript heap out of memory|out of memory|Cannot allocate memory|ENOMEM"),
        "oom_timeout",
        3,
    ),
    SignatureRule("disk.full", "disk", _r(r"No space left on device"), "oom_timeout", 3),
    SignatureRule(
        "timeout.job",
        "timeout",
        _r(r"has exceeded the maximum execution time|The operation was canceled|timed out after"),
        "oom_timeout",
        2,
    ),
    # generic, no category
    SignatureRule("gha.error", "annotation", re.compile(r"##\[error\](.+)"), None, 1, 1),
    SignatureRule(
        "exit.code", "exit_code", _r(r"Process completed with exit code (\d+)"), None, 1, 1
    ),
)

_PREFILTER = re.compile(
    r"error|fail|denied|refused|not found|no such|missing|killed|exit code|timed out|timeout|"
    r"canceled|403|memory|enomem|cannot|could not|unable|exception|fatal|forbidden|"
    r"credentials|does not exist|not accessible|no module|no matching|resolutionimpossible|"
    r"enoent|no space|is the server running|tests:|tests run:|--- fail|composer\.json requires",
    re.IGNORECASE,
)


def extract_signatures(lines: list[str]) -> list[SignatureMatch]:
    found: list[SignatureMatch] = []
    for number, raw_line in enumerate(lines, start=1):
        line = strip_timestamp(raw_line)
        if not _PREFILTER.search(line):
            continue
        for rule in RULES:
            match = rule.pattern.search(line)
            if match is None:
                continue
            value = rule.rule_id
            if rule.value_group is not None:
                groups = [g for g in match.groups() if g]
                value = (match.group(rule.value_group) or (groups[0] if groups else "")).strip()
            found.append(
                SignatureMatch(
                    line_number=number,
                    rule_id=rule.rule_id,
                    kind=rule.kind,
                    value=value[:300] or rule.rule_id,
                    category=rule.category,
                    weight=rule.weight,
                    excerpt=line.strip()[:500],
                )
            )
    if len(found) > MAX_SIGNATURES:
        # Keep the strongest, then the earliest; return in line order.
        keep = sorted(found, key=lambda s: (-s.weight, s.line_number))[:MAX_SIGNATURES]
        found = sorted(keep, key=lambda s: s.line_number)
    return found
