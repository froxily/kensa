"""Running change analysis for a GitHub import (v1.1, D-054). Network only, before the
investigation is stored; the agent worker never calls GitHub (D-031)."""

from kensa.analysis.causes import assess_causes
from kensa.analysis.classifier import classify
from kensa.analysis.signatures import extract_signatures
from kensa.changes.analyzer import ChangeAnalysis, analyze
from kensa.changes.sources import GitHubChangeSource, failed_run_facts, known_blobs
from kensa.core.config import Settings
from kensa.github.client import GitHubClient, GitHubError
from kensa.github.importer import GitHubImport
from kensa.history.github import BudgetExhaustedError, RequestBudget

SUBJECT_MIN_WEIGHT = 2


def failure_subjects(lines: list[str]) -> tuple[list[str], str]:
    """What failed (variables, modules, tests, images) and the rule category, from the log."""
    signatures = extract_signatures(lines)
    causes = assess_causes(lines)
    rule = classify(signatures, causes)
    subjects = [c.subject for c in causes.lines if c.subject]
    subjects += [
        s.value for s in signatures if s.value != s.rule_id and s.weight >= SUBJECT_MIN_WEIGHT
    ]
    return list(dict.fromkeys(subjects)), rule.category


def analyze_import(
    client: GitHubClient, imported: GitHubImport, settings: Settings
) -> ChangeAnalysis:
    """Compare the imported run with the last comparable success, within the request budget.
    Any GitHub failure or an exhausted budget means the history is unavailable (uncertainty,
    never an assumption that nothing changed)."""
    failed, job_name = failed_run_facts(imported)
    lines = imported.log_text.split("\n")
    subjects, category = failure_subjects(lines)
    source = GitHubChangeSource(
        client,
        imported.repo.owner,
        imported.repo.repo,
        imported.run.workflow_id,
        RequestBudget(settings.change_request_budget),
        known_blobs(imported.files, imported.run.head_sha),
    )
    try:
        return analyze(failed, job_name, lines, source, subjects=subjects, category=category)
    except BudgetExhaustedError:
        reason = "The request budget for comparing runs ran out."
    except GitHubError as exc:
        reason = f"GitHub could not provide the history ({exc.code})."
    return ChangeAnalysis("history_unavailable", [reason])
