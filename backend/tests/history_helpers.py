"""Shared builders for the v1.1 history tests: canned GitHub responses (no network), a fake
client that answers them, and a fully populated GitHub investigation for purge tests."""

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from kensa.db.models import (
    AgentEvent,
    Chunk,
    Citation,
    Diagnosis,
    Document,
    Evidence,
    RemediationProposal,
)
from kensa.github.client import GitHubClient, GitHubError
from kensa.github.importer import GitHubImport, JobInfo, RepoInfo, RunInfo, StepInfo
from kensa.history.github import HistoryReader, RequestBudget
from kensa.investigations.service import create_github_investigation

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


def sha(n: int) -> str:
    return f"{n:040x}"


def run_json(
    run_id: int,
    *,
    attempt: int = 1,
    conclusion: str | None = "success",
    status: str = "completed",
    created: datetime | None = None,
    workflow_id: int = 7,
    path: str = ".github/workflows/ci.yml",
    branch: str = "main",
    head_sha: str | None = None,
    private: bool = False,
) -> dict[str, Any]:
    created = created or NOW - timedelta(hours=run_id % 1000)
    return {
        "id": run_id,
        "run_attempt": attempt,
        "run_number": run_id % 10_000,
        "workflow_id": workflow_id,
        "path": path,
        "name": "ci",
        "event": "push",
        "head_branch": branch,
        "head_sha": head_sha or sha(run_id),
        "status": status,
        "conclusion": conclusion if status == "completed" else None,
        "created_at": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_started_at": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "updated_at": (created + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repository": {"private": private},
        "actor": {"login": "someone"},  # never stored
    }


def job_json(
    job_id: int, run_id: int, *, attempt: int = 1, conclusion: str = "failure"
) -> dict[str, Any]:
    return {
        "id": job_id,
        "run_id": run_id,
        "run_attempt": attempt,
        "name": "test (3.12)",
        "status": "completed",
        "conclusion": conclusion,
        "started_at": "2026-11-09T10:00:00Z",
        "completed_at": "2026-11-09T10:04:00Z",
        "labels": ["ubuntu-24.04"],
        "runner_name": "GitHub Actions 7",
        "steps": [
            {"number": 1, "name": "Set up job", "conclusion": "success"},
            {"number": 2, "name": "Run tests", "conclusion": conclusion},
        ],
    }


def _utc(value: str | None) -> datetime:
    """A GitHub time (or a bare date in a range); a malformed run without one sorts last."""
    if not value:
        return datetime.min.replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class FakeClient:
    """Answers HistoryReader's GET requests from canned data, like GitHub would."""

    def __init__(self) -> None:
        self.runs: list[dict[str, Any]] = []
        self.attempts: dict[tuple[int, int], dict[str, Any]] = {}
        self.jobs: dict[tuple[int, int], list[dict[str, Any]]] = {}
        self.repository: dict[str, Any] = {"default_branch": "main", "private": False}
        self.calls: list[str] = []
        self.fail_with: GitHubError | None = None

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def get_json(self, path: str, params: dict[str, str | int] | None = None, *, what: str) -> Any:
        self.calls.append(path)
        if self.fail_with is not None:
            raise self.fail_with
        if path.endswith("/actions/runs"):
            page = int((params or {}).get("page", 1))
            listed = self.runs
            if created := str((params or {}).get("created", "")):
                # GitHub's inclusive range on the creation time, newest first.
                start, end = created.split("..")
                since = _utc(start)
                until = _utc(end + "T23:59:59Z" if len(end) == 10 else end)  # a date: whole day
                listed = sorted(
                    (
                        r
                        for r in self.runs
                        if "created_at" not in r or since <= _utc(r["created_at"]) <= until
                    ),
                    key=lambda r: _utc(r.get("created_at")),
                    reverse=True,
                )
            items = listed[(page - 1) * 100 : page * 100]
            return {"total_count": len(listed), "workflow_runs": items}
        if match := re.search(r"/runs/(\d+)/attempts/(\d+)/jobs$", path):
            key = (int(match[1]), int(match[2]))
            page = int((params or {}).get("page", 1))
            return {"jobs": self.jobs.get(key, [])[(page - 1) * 100 : page * 100]}
        if match := re.search(r"/runs/(\d+)/attempts/(\d+)$", path):
            key = (int(match[1]), int(match[2]))
            if key in self.attempts:
                return self.attempts[key]
            return next(r for r in self.runs if (r["id"], r["run_attempt"]) == key)
        if match := re.search(r"/runs/(\d+)$", path):
            run_id = int(match[1])
            return next(r for r in self.runs if r["id"] == run_id)
        if re.fullmatch(r"/repos/[^/]+/[^/]+", path):
            return self.repository
        raise AssertionError(f"unexpected request {path}")


def reader(client: FakeClient, budget: int = 300) -> HistoryReader:
    return HistoryReader(cast(GitHubClient, client), RequestBudget(budget))


def github_import(
    owner: str, repo: str, log_text: str, *, run_id: int, job_id: int
) -> GitHubImport:
    return GitHubImport(
        repo=RepoInfo(owner, repo, f"https://github.com/{owner}/{repo}", private=False),
        run=RunInfo(
            id=run_id,
            name="ci",
            display_title="ci",
            run_number=1,
            run_attempt=1,
            event="push",
            status="completed",
            conclusion="failure",
            head_branch="main",
            head_sha=sha(run_id),
            workflow_path=".github/workflows/ci.yml",
            html_url=f"https://github.com/{owner}/{repo}/actions/runs/{run_id}",
            created_at="2026-11-09T10:00:00Z",
        ),
        job=JobInfo(
            id=job_id,
            name="test",
            conclusion="failure",
            html_url=f"https://github.com/{owner}/{repo}/actions/runs/{run_id}/job/{job_id}",
            failed_steps=(StepInfo(2, "Run tests", "failure"),),
        ),
        log_text=log_text,
        log_source="github",
        log_dropped_lines=0,
    )


def populated_investigation(
    engine: Engine,
    workspace_id: uuid.UUID,
    owner: str,
    repo: str,
    marker: str,
    *,
    run_id: int,
    job_id: int,
) -> uuid.UUID:
    """A GitHub investigation whose every derived record carries ``marker``: log chunks,
    signatures, evidence, a diagnosis and citation, a timeline event, a proposal diff, an
    incident document and LangGraph checkpoint rows."""
    log = (
        "2026-11-09T10:00:00.0000000Z ##[group]Run tests\n"
        f"2026-11-09T10:00:01.0000000Z KeyError: '{marker}'\n"
        "2026-11-09T10:00:02.0000000Z ##[error]Process completed with exit code 1.\n"
    )
    with Session(engine) as session, session.begin():
        investigation = create_github_investigation(
            session,
            workspace_id,
            github_import(owner, repo, log, run_id=run_id, job_id=job_id),
            "mock",
            None,
        )
        investigation_id = investigation.id
        chunk = (
            session.query(Chunk)
            .filter(Chunk.workspace_id == workspace_id)
            .filter(Chunk.content.contains(marker))
            .first()
        )
        assert chunk is not None
        session.add(
            Evidence(
                workspace_id=workspace_id,
                investigation_id=investigation_id,
                chunk_id=chunk.id,
                label="E1",
                rank=1,
                score=1.0,
                channels=["signature"],
            )
        )
        diagnosis = Diagnosis(
            workspace_id=workspace_id,
            investigation_id=investigation_id,
            category="missing_env_var",
            summary=f"{marker} is missing",
            root_cause=f"The variable {marker} is not set.",
            confidence=0.5,
            uncertainty="",
            recommended_fixes=[f"Set {marker}"],
            verification_status="plausible",
            verification_notes=[],
            provider="mock",
        )
        session.add(diagnosis)
        session.flush()
        session.add(
            Citation(
                workspace_id=workspace_id,
                diagnosis_id=diagnosis.id,
                ordinal=1,
                chunk_id=chunk.id,
                evidence_label="E1",
                line_number=2,
                quote=f"KeyError: '{marker}'",
                valid=True,
            )
        )
        session.add(
            AgentEvent(
                workspace_id=workspace_id,
                investigation_id=investigation_id,
                seq=99,
                attempt=1,
                node="diagnose",
                event_type="info",
                summary=f"Diagnosed {marker}",
                detail={"quote": marker},
            )
        )
        session.add(
            RemediationProposal(
                workspace_id=workspace_id,
                investigation_id=investigation_id,
                ordinal=1,
                title="Set the variable",
                action=f"Add {marker} to the workflow env.",
                origin="template",
                diff=f"+  {marker}: ${{{{ secrets.X }}}}",
            )
        )
        incident = Document(
            workspace_id=workspace_id,
            source_type="incident",
            name=f"incident/{investigation_id}",
            content=f"# Incident\n{marker}\n",
            content_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            byte_size=10,
            line_count=2,
        )
        session.add(incident)
        session.flush()
        session.add(
            Chunk(
                workspace_id=workspace_id,
                document_id=incident.id,
                ordinal=0,
                kind="window",
                start_line=1,
                end_line=2,
                content=f"# Incident\n{marker}\n",
                content_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            )
        )
        thread = f"investigation-{investigation_id}"
        session.execute(
            text(
                "INSERT INTO langgraph.checkpoints (thread_id, checkpoint_id, checkpoint) "
                "VALUES (:t, 'c1', CAST(:c AS jsonb))"
            ),
            {"t": thread, "c": f'{{"evidence": "{marker}"}}'},
        )
        session.execute(
            text(
                "INSERT INTO langgraph.checkpoint_blobs (thread_id, channel, version, type, blob) "
                "VALUES (:t, 'evidence', '1', 'json', :b)"
            ),
            {"t": thread, "b": marker.encode()},
        )
        session.execute(
            text(
                "INSERT INTO langgraph.checkpoint_writes "
                "(thread_id, checkpoint_id, task_id, idx, channel, blob) "
                "VALUES (:t, 'c1', 'task', 0, 'evidence', :b)"
            ),
            {"t": thread, "b": marker.encode()},
        )
    return investigation_id


def marker_locations(engine: Engine, marker: str) -> list[str]:
    """Every column, in every table of the public and langgraph schemas, that still holds
    ``marker`` (text, JSON, arrays and bytes)."""
    found: list[str] = []
    with engine.connect() as conn:
        columns = conn.execute(
            text(
                "SELECT table_schema, table_name, column_name, data_type "
                "FROM information_schema.columns "
                "WHERE table_schema IN ('public', 'langgraph') "
                "AND data_type IN ('text', 'character varying', 'jsonb', 'bytea', 'ARRAY')"
            )
        ).all()
        for schema, table, column, data_type in columns:
            target = f'"{schema}"."{table}"'
            if data_type == "bytea":
                condition = f'position(CAST(:needle AS bytea) in "{column}") > 0'
                params: dict[str, Any] = {"needle": marker.encode()}
            else:
                condition = f'CAST("{column}" AS text) LIKE :needle'
                params = {"needle": f"%{marker}%"}
            # Identifiers come from information_schema, never from data.
            sql = f"SELECT count(*) FROM {target} WHERE {condition}"  # noqa: S608
            if conn.execute(text(sql), params).scalar_one():
                found.append(f"{schema}.{table}.{column}")
    return found
