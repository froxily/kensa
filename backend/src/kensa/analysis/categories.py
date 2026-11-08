"""The failure categories Kensa diagnoses. Shared by the rules, the LLM schema and evaluation."""

from typing import Literal, get_args

Category = Literal[
    "missing_env_var",
    "dependency_build",
    "github_permissions",
    "db_connectivity",
    "docker",
    "workflow_path",
    "test_regression",
    "oom_timeout",
    "unknown",
]
CATEGORIES: tuple[Category, ...] = get_args(Category)

CATEGORY_DESCRIPTIONS: dict[Category, str] = {
    "missing_env_var": "a required environment variable or secret is not set",
    "dependency_build": "dependency resolution, installation, compilation or build failure",
    "github_permissions": "the workflow token or credentials lack a permission (HTTP 403, denied)",
    "db_connectivity": "the job cannot reach or authenticate to a database service",
    "docker": "Docker daemon, image pull or image build failure",
    "workflow_path": "a file, directory or action path referenced by the workflow does not exist",
    "test_regression": "tests ran and one or more assertions failed",
    "oom_timeout": "the job ran out of memory or disk, was killed, or timed out",
    "unknown": "the evidence does not establish a cause",
}
