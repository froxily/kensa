"""Structural checks on model-proposed edits (M4 live finding).

The first live run produced an edit that passed the textual checks but deleted a step's ``env``
and ``run`` keys and cut ``working-directory: ingest`` to ``ing``; the result even parsed as YAML.
These tests reproduce that shape on an invented workflow.
"""

import uuid

import pytest

from kensa.agents.evidence import EvidenceItem
from kensa.agents.remediation import Proposal, RepositoryFile, structure_problem, validate_edit
from kensa.agents.schemas import EDIT_TEXT_MAX, EditDraft

WORKFLOW = """name: Ingest
on:
  schedule:
    - cron: "0 3 * * *"
jobs:
  ingest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Ingest every source
        working-directory: ingest
        env:
          APP_DATABASE_URL: ${{ secrets.APP_DATABASE_URL }}
          REVIEWED: ${{ inputs.reviewed }}
        run: |
          uv run --locked app ingest-all
"""
PATH = ".github/workflows/ingest.yml"
DOC_ID = uuid.uuid4()
FILES = {DOC_ID: RepositoryFile(DOC_ID, PATH, WORKFLOW)}
EVIDENCE = {
    "E1": EvidenceItem(
        label="E1",
        chunk_id=uuid.uuid4(),
        document_name=PATH,
        step_name=None,
        start_line=1,
        end_line=16,
        lines=tuple(WORKFLOW.split("\n")[:16]),
        score=0.1,
        channels=("fts",),
        source_type="workflow_yaml",
    )
}
STEP = """      - name: Ingest every source
        working-directory: ingest
        env:
          APP_DATABASE_URL: ${{ secrets.APP_DATABASE_URL }}
          REVIEWED: ${{ inputs.reviewed }}
        run: |"""


def _edit(find: str, replace: str) -> EditDraft:
    return EditDraft(evidence_id="E1", find=find, replace=replace, explanation="Add a check.")


def test_the_live_runs_destructive_edit_is_dropped() -> None:
    replace = """      - name: Check the database socket
        run: |
          test -S /var/run/postgresql/.s.PGSQL.5432 || exit 1

      - name: Ingest every source
        working-directory: ing
"""
    assert validate_edit(_edit(STEP, replace), EVIDENCE, FILES) == "removes_existing_keys"


def test_an_additive_edit_is_kept() -> None:
    find = "          REVIEWED: ${{ inputs.reviewed }}"
    replace = find + "\n          APP_LOG_LEVEL: debug"
    proposal = validate_edit(_edit(find, replace), EVIDENCE, FILES)
    assert isinstance(proposal, Proposal)
    assert proposal.diff is not None
    assert "+          APP_LOG_LEVEL: debug" in proposal.diff


RUN_LINE = "          uv run --locked app ingest-all"


def test_the_final_live_runs_secret_printing_broken_script_is_dropped() -> None:
    # Second live finding: valid YAML, but the script prints a secret-backed variable and leaves
    # "if [[ \" dangling.
    replace = (
        '          echo "Validating database URL: $APP_DATABASE_URL"\n'
        "          if [[ \\\n" + RUN_LINE
    )
    assert validate_edit(_edit(RUN_LINE, replace), EVIDENCE, FILES) == "exposes_secret"


@pytest.mark.parametrize(
    ("added", "problem"),
    [
        ('          echo "Using ${APP_DATABASE_URL}"', "exposes_secret"),
        ('          printf "%s" "$APP_DATABASE_URL"', "exposes_secret"),
        ('          if [ -n "$REVIEWED" ]; then', "breaks_shell"),
        ("          if [[ \\", "breaks_shell"),
        ('          echo "unterminated', "breaks_shell"),
        ('          echo "Starting the ingest"', None),
        ('          echo "Reviewed: $REVIEWED"', None),  # not a secret
        ('          if [ -z "$APP_DATABASE_URL" ]; then echo "URL is empty"; exit 1; fi', None),
    ],
)
def test_changed_run_scripts_are_checked(added: str, problem: str | None) -> None:
    outcome = validate_edit(_edit(RUN_LINE, added + "\n" + RUN_LINE), EVIDENCE, FILES)
    if problem is None:
        assert isinstance(outcome, Proposal)
    else:
        assert outcome == problem


def test_a_new_step_must_be_runnable() -> None:
    find = "      - uses: actions/checkout@v4"
    replace = find + "\n      - name: A step that does nothing"
    assert validate_edit(_edit(find, replace), EVIDENCE, FILES) == "breaks_workflow"


def test_an_edit_that_breaks_yaml_is_dropped() -> None:
    find = "        working-directory: ingest"
    replace = "        working-directory: [ingest"
    assert validate_edit(_edit(find, replace), EVIDENCE, FILES) == "breaks_syntax"


def test_an_edit_at_the_length_cap_counts_as_truncated() -> None:
    find = "          REVIEWED: ${{ inputs.reviewed }}"
    replace = (find + "\n          # " + "x" * EDIT_TEXT_MAX)[:EDIT_TEXT_MAX]
    assert validate_edit(_edit(find, replace), EVIDENCE, FILES) == "truncated"


@pytest.mark.parametrize(
    ("path", "before", "after", "problem"),
    [
        ("app/main.py", "def f():\n    return 1\n", "def f(:\n    return 1\n", "breaks_syntax"),
        ("app/main.py", "def f():\n    return 1\n", "def f():\n    return 2\n", None),
        ("package.json", '{"a": 1}', '{"a": 1,}', "breaks_syntax"),
        ("pyproject.toml", 'name = "x"\n', 'name = "x\n', "breaks_syntax"),
        ("config.yml", "a: 1\nb: 2\n", "a: 1\n", "removes_existing_keys"),
        ("config.yml", "a: [unclosed\n", "a: 1\n", None),  # unparsable before: not judged
        ("README.md", "# Title\n", "", None),  # no structure to check
    ],
)
def test_structure_checks_by_file_type(
    path: str, before: str, after: str, problem: str | None
) -> None:
    assert structure_problem(path, before, after) == problem
