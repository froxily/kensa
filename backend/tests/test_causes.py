"""Cause-level evidence (M5.1): statements of an underlying cause, not symptoms."""

import pytest

from kensa.analysis.causes import assess_causes, causes_from_json, causes_to_json
from kensa.analysis.classifier import classify
from kensa.analysis.signatures import extract_signatures

STAMP = "2026-10-30T10:00:00.0000000Z "


def categories(*lines: str) -> set[str]:
    return set(assess_causes([STAMP + line for line in lines]).categories)


@pytest.mark.parametrize(
    ("line", "category"),
    [
        ("start: PAYMENTS_REGION must be set", "missing_env_var"),
        ("Error: environment variable SMTP_HOST is not set", "missing_env_var"),
        ("E   KeyError: 'API_BASE_URL'", "missing_env_var"),
        ("./deploy.sh: line 4: DEPLOY_TARGET: unbound variable", "missing_env_var"),
        ("Could not resolve placeholder 'audit.sink.url' in value", "missing_env_var"),
        ("Error: Input required and not supplied: token", "missing_env_var"),
        ("RequestError [HttpError]: Resource not accessible by integration", "github_permissions"),
        ("ERROR: denied: permission_denied: write_package", "github_permissions"),
        (
            "remote: Permission to acme/site.git denied to github-actions[bot].",
            "github_permissions",
        ),
        ('FATAL:  password authentication failed for user "app"', "db_connectivity"),
        ("dial tcp [::1]:6379: connect: connection refused", "db_connectivity"),
        ("Access denied for user 'ci'@'172.18.0.1' (using password: YES)", "db_connectivity"),
        ("Cannot connect to the Docker daemon at unix:///var/run/docker.sock.", "docker"),
        ('ERROR: failed to compute cache key: "/dist": not found', "docker"),
        ("ERROR: Could not open requirements file: [Errno 2] No such file", "workflow_path"),
        ("MSBUILD : error MSB1009: Project file does not exist.", "workflow_path"),
        ("ModuleNotFoundError: No module named 'yaml'", "dependency_build"),
        ("error[E0599]: no method named `frobnicate` found", "dependency_build"),
        ("##[error]Process completed with exit code 137.", "oom_timeout"),
        ("FATAL ERROR: Reached heap limit - JavaScript heap out of memory", "oom_timeout"),
        ("    rounding_test.go:12: got 2.0, want 3.0", "test_regression"),
        ("Expected: 200", "test_regression"),
    ],
)
def test_cause_statements(line: str, category: str) -> None:
    assert category in categories(line)


@pytest.mark.parametrize(
    "line",
    [
        "--- FAIL: TestStartup (0.00s)",  # a symptom
        "FAILED tests/test_api.py::test_health - assert 500 == 200",  # symptom (the assert is data)
        "ERROR: failed to solve: process did not complete successfully: exit code: 1",
        "##[error]Process completed with exit code 1.",
        "Region is required",  # no upper-case variable name
        "Tests: 2 failed, 40 passed, 42 total",
    ],
)
def test_symptoms_and_prose_are_not_environmental_causes(line: str) -> None:
    found = categories(line)
    assert not (found - {"test_regression"})


def test_text_a_test_asserts_on_is_not_the_environment() -> None:
    found = categories(
        'Expected: "Missing variable: REGION_CODE"',
        '    config_test.go:30: expected error "API_URL must be set", got nil',
    )
    assert found == {"test_regression"}


def test_an_empty_variable_in_a_steps_environment_is_a_stated_cause() -> None:
    evidence = assess_causes(
        [
            STAMP + "##[group]Run uv run ingest",
            STAMP + "uv run ingest",
            STAMP + "shell: /usr/bin/bash -e {0}",
            STAMP + "env:",
            STAMP + "  INGEST_DATABASE_URL: ",
            STAMP + "  LOG_LEVEL: info",
            STAMP + "  API_TOKEN: ***",
            STAMP + "##[endgroup]",
            STAMP + "psql: error: connection to server on socket failed: No such file",
        ]
    )
    empty = evidence.for_category("missing_env_var")
    assert [(c.line_number, c.subject) for c in empty] == [(5, "INGEST_DATABASE_URL")]
    assert "db_connectivity" in evidence.categories
    assert evidence.competing("db_connectivity") == {"missing_env_var"}


def test_competing_causes_ignore_the_test_symptom() -> None:
    evidence = assess_causes(
        [STAMP + "E   KeyError: 'API_BASE_URL'", STAMP + "    handler_test.go:9: got 1, want 2"]
    )
    assert evidence.competing("missing_env_var") == frozenset()
    assert evidence.competing("test_regression") == {"missing_env_var"}


def test_a_stated_environmental_cause_outranks_the_failing_test_that_reports_it() -> None:
    lines = [
        STAMP + "=== RUN   TestStartup",
        STAMP + "    startup_test.go:24: start: PAYMENTS_REGION must be set",
        STAMP + "--- FAIL: TestStartup (0.00s)",
        STAMP + "FAIL",
    ]
    signatures = extract_signatures(lines)
    assert classify(signatures).category == "test_regression"  # the symptom alone
    rule = classify(signatures, assess_causes(lines))
    assert rule.category == "missing_env_var"
    assert 2 in rule.supporting_lines


def test_a_genuine_regression_stays_a_regression() -> None:
    lines = [
        STAMP + "=== RUN   TestRounding",
        STAMP + "    round_test.go:12: got 2, want 3",
        STAMP + "--- FAIL: TestRounding (0.00s)",
        STAMP + '    config_test.go:30: expected error "API_URL must be set", got nil',
    ]
    rule = classify(extract_signatures(lines), assess_causes(lines))
    assert rule.category == "test_regression"


@pytest.mark.parametrize(
    ("line", "category"),
    [
        (
            '** (System.EnvError) could not fetch environment variable "LEDGER_ZONE" '
            "because it is not set",
            "missing_env_var",
        ),
        ("PAYOUT_SHARD not configured: NotPresent", "missing_env_var"),
        ("Redis: -ERR DB index is out of range", "db_connectivity"),
        ("dial tcp: lookup sessions-db on 127.0.0.53:53: no such host", "db_connectivity"),
        ("Unhandled exception. System.OutOfMemoryException: Exception of type", "oom_timeout"),
        ("PHP Fatal error:  Allowed memory size of 8388608 bytes exhausted", "oom_timeout"),
        ("make: *** No rule to make target 'gen/schema.h', needed by 'all'.", "workflow_path"),
        ('PHP Parse error:  syntax error, unexpected token "}"', "dependency_build"),
        ("      Assertion with == failed", "test_regression"),
    ],
)
def test_more_tool_phrasings(line: str, category: str) -> None:
    assert category in categories(line)


def test_a_quoted_value_is_not_a_statement_about_the_environment() -> None:
    # ExUnit prints compared values as left:/right: lines; the quoted text is data under test.
    assert categories('      right: "missing environment variable: LEDGER_POLICY"') == {
        "test_regression"
    }
    assert categories('Notice text was "LEDGER_POLICY must be set" before the change') == set()


def test_assertions_count_weakly_against_a_stated_environmental_cause() -> None:
    lines = [
        STAMP + "    Assert.Equal() Failure: Values differ",
        STAMP + "Expected: 0",
        STAMP + "Actual:   1",
        STAMP + "ERROR: failed to solve: node:22-alpine: failed to resolve source metadata",
    ]
    assert classify(extract_signatures(lines), assess_causes(lines)).category == "docker"


def test_json_round_trip() -> None:
    evidence = assess_causes([STAMP + "start: PAYMENTS_REGION must be set"])
    assert causes_from_json(causes_to_json(evidence)) == evidence
