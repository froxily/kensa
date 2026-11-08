"""Deterministic remediation templates used by rules-only (mock) diagnoses."""

from kensa.analysis.categories import Category

FIX_TEMPLATES: dict[Category, list[str]] = {
    "missing_env_var": [
        "Define the missing variable for this job (repository or environment secret, or an "
        "`env:` entry) and check that the name matches exactly.",
        "If it is a secret, confirm the workflow can read it: environment protection rules "
        "and pull requests from forks do not receive secrets.",
    ],
    "dependency_build": [
        "Reproduce the install or build locally with the same lockfile and tool versions.",
        "Resolve the conflicting or missing package by updating or pinning a compatible "
        "version, rather than forcing the resolution.",
    ],
    "github_permissions": [
        "Grant only the `permissions:` this job needs (for example `contents: write` to "
        "create a release) at job level.",
        "Check whether the run comes from a fork, where the token is read-only.",
    ],
    "db_connectivity": [
        "Make sure the database service is defined and healthy before tests start "
        "(service container with a health check).",
        "Check that the host, port, database name and credentials used by the tests match "
        "the service configuration.",
    ],
    "docker": [
        "Check that the image name, tag and registry credentials are correct and that the "
        "Dockerfile builds locally.",
    ],
    "workflow_path": [
        "Fix the referenced path: compare the file name and `working-directory` with the "
        "repository layout at this commit.",
    ],
    "test_regression": [
        "Run the failing test locally on this commit and inspect the assertion difference.",
        "Fix the code, or update the test only if the behaviour change is intended.",
    ],
    "oom_timeout": [
        "Find what consumes the memory, disk or time; raise limits or timeouts only once "
        "the workload is confirmed to need them.",
    ],
    "unknown": [
        "Inspect the log around the last error lines and re-run the investigation with more "
        "context (the workflow file and recent changes).",
    ],
}
