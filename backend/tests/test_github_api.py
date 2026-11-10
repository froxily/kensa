"""M4 end to end through the API, with GitHub mocked by sanitized fixtures (no live calls)."""

import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from kensa.agents.handler import make_investigate_handler, on_job_outcome
from kensa.app import create_app
from kensa.core.config import Settings
from kensa.db.models import Document, Investigation, Repository, WorkflowRun
from kensa.github.client import SHARED_CACHE
from kensa.investigations.service import INVESTIGATE_JOB, RESUME_JOB
from kensa.jobs.worker import Worker
from tests.github_fixtures import (
    API,
    CONFIG_PY,
    JOB_ID,
    JOBS_PATH,
    LOG,
    LOGS_PATH,
    OTHER_SHA,
    OWNER,
    REPO,
    RUN_ID,
    RUN_PATH,
    RUN_URL,
    SHA,
    SIGNATURE,
    STORE_HOST,
    STORE_URL,
    WORKFLOW,
    contents_json,
    jobs_json,
    run_json,
    runs_json,
)

pytestmark = pytest.mark.db
TOKEN = "github_pat_" + "Z9y8X7w6V5u4T3s2R1q0" * 3


class Api:
    def __init__(self, client: TestClient, engine: Engine, settings: Settings) -> None:
        self.client, self.engine, self.settings = client, engine, settings

    def work(self) -> None:
        handler = make_investigate_handler(self.settings)
        handlers = {INVESTIGATE_JOB: handler, RESUME_JOB: handler}
        Worker(self.engine, handlers, on_outcome=on_job_outcome).run_once()


def _api(engine_url: str, token: str | None) -> Iterator[Api]:
    settings = Settings(
        _env_file=None,
        database_url=engine_url,
        worker_enabled=False,
        inference_provider="mock",
        embedding_provider="mock",
        github_token=SecretStr(token) if token else None,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        yield Api(client, app.state.engine, settings)


@pytest.fixture
def api(db_engine: Engine, test_database_url: str) -> Iterator[Api]:
    yield from _api(test_database_url, TOKEN)


@pytest.fixture
def anonymous(db_engine: Engine, test_database_url: str) -> Iterator[Api]:
    yield from _api(test_database_url, None)


@pytest.fixture
def github() -> Iterator[respx.MockRouter]:
    SHARED_CACHE._items.clear()  # each test starts with an empty conditional-request cache
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        router.route(host="testserver").pass_through()
        yield router


def _mock_run(router: respx.MockRouter, sha: str = SHA) -> dict[str, respx.Route]:
    routes = {
        "run": router.get(f"{API}{RUN_PATH}").mock(
            return_value=httpx.Response(200, json=run_json(head_sha=sha))
        ),
        "jobs": router.get(f"{API}{JOBS_PATH}").mock(
            return_value=httpx.Response(200, json=jobs_json())
        ),
        "logs": router.get(f"{API}{LOGS_PATH}").mock(
            return_value=httpx.Response(302, headers={"location": STORE_URL})
        ),
        "store": router.get(host=STORE_HOST).mock(
            return_value=httpx.Response(
                200, content=LOG.encode(), headers={"content-type": "text/plain; charset=utf-8"}
            )
        ),
        "workflow": router.get(
            f"{API}/repos/{OWNER}/{REPO}/contents/.github/workflows/test.yml"
        ).mock(return_value=httpx.Response(200, json=contents_json("x", WORKFLOW))),
        "config": router.get(f"{API}/repos/{OWNER}/{REPO}/contents/src/demo/config.py").mock(
            return_value=httpx.Response(200, json=contents_json("src/demo/config.py", CONFIG_PY))
        ),
        "conftest": router.get(f"{API}/repos/{OWNER}/{REPO}/contents/tests/conftest.py").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        ),
    }
    return routes


def _create(api: Api, **extra: Any) -> Any:
    body = {
        "source": "github",
        "provider": "mock",
        "github": {"owner": OWNER, "repo": REPO, "run_id": RUN_ID, "job_id": JOB_ID},
        **extra,
    }
    return api.client.post("/api/investigations", json=body)


def test_lookup_lists_failed_runs_then_failed_jobs(api: Api, github: respx.MockRouter) -> None:
    github.get(f"{API}/repos/{OWNER}/{REPO}/actions/runs").mock(
        return_value=httpx.Response(200, json=runs_json())
    )
    _mock_run(github)
    repo = api.client.post("/api/github/lookup", json={"url": f"https://github.com/{OWNER}/{REPO}"})
    assert repo.status_code == 200, repo.text
    assert repo.json()["kind"] == "repository"
    assert [r["id"] for r in repo.json()["runs"]] == [RUN_ID]
    assert repo.json()["token_configured"] is True

    run = api.client.post("/api/github/lookup", json={"url": f"{RUN_URL}/job/{JOB_ID}?pr=3"})
    assert run.status_code == 200, run.text
    body = run.json()
    assert (body["kind"], body["selected_job_id"]) == ("run", JOB_ID)
    assert [j["id"] for j in body["jobs"]] == [JOB_ID]
    assert body["jobs"][0]["failed_steps"] == [
        {"number": 4, "name": "Run tests", "conclusion": "failure"}
    ]
    assert body["run"]["head_sha"] == SHA


@pytest.mark.parametrize(
    ("url", "status"),
    [
        ("http://github.com/o/r", 422),
        ("https://example.com/o/r", 422),
        ("https://github.com/o/r/actions/runs/1/logs", 422),
    ],
)
def test_lookup_refuses_unsupported_urls_without_calling_github(
    api: Api, github: respx.MockRouter, url: str, status: int
) -> None:
    response = api.client.post("/api/github/lookup", json={"url": url})
    assert response.status_code == status
    assert not [c for c in github.calls if c.request.url.host != "testserver"]


def test_rate_limits_and_missing_runs_are_explained(api: Api, github: respx.MockRouter) -> None:
    github.get(f"{API}{RUN_PATH}").mock(
        return_value=httpx.Response(
            403,
            json={"message": "API rate limit exceeded"},
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1793348428"},
        )
    )
    limited = api.client.post("/api/github/lookup", json={"url": RUN_URL})
    assert limited.status_code == 429
    assert "rate limit" in limited.json()["detail"]
    github.get(f"{API}{RUN_PATH}").mock(return_value=httpx.Response(404, json={"message": "x"}))
    missing = api.client.post("/api/github/lookup", json={"url": RUN_URL})
    assert missing.status_code == 404


def test_a_failed_run_becomes_a_commit_pinned_investigation(
    api: Api, github: respx.MockRouter
) -> None:
    routes = _mock_run(github)
    created = _create(api)
    assert created.status_code == 201, created.text
    investigation_id = created.json()["id"]
    assert created.json()["source"] == "github"
    # Only reads, the token only on api.github.com, nothing on the log store.
    assert {c.request.method for c in github.calls} == {"GET"}
    assert routes["logs"].calls[0].request.headers["authorization"] == f"Bearer {TOKEN}"
    assert "authorization" not in routes["store"].calls[0].request.headers

    api.work()
    detail = api.client.get(f"/api/investigations/{investigation_id}").json()
    run = detail["github_run"]
    assert (run["run_id"], run["job_id"], run["head_sha"]) == (RUN_ID, JOB_ID, SHA)
    assert run["failed_steps"] == ["4. Run tests"]
    assert run["log_source"] == "github"
    assert run["files_fetched"] == [".github/workflows/test.yml", "src/demo/config.py"]
    assert run["files_missing"] == ["tests/conftest.py"]
    assert SIGNATURE not in str(detail)

    diagnosis = detail["diagnosis"]
    assert diagnosis["category"] == "missing_env_var"
    repository_evidence = [e for e in detail["evidence"] if e["source_type"] != "log"]
    for item in repository_evidence:  # every repository excerpt is pinned to the run's commit
        assert item["commit_sha"] == SHA
        assert item["source_url"].startswith(f"https://github.com/{OWNER}/{REPO}/blob/{SHA}/")
    timeline = api.client.get(f"/api/investigations/{investigation_id}/events").json()
    assert timeline[0]["node"] == "github"
    assert "at commit 0123456" in timeline[0]["summary"]


def test_importing_the_same_job_again_opens_its_investigation(
    api: Api, github: respx.MockRouter
) -> None:
    """v1.1: no duplicate investigations of one job attempt (same commit, same provider)."""
    _mock_run(github)
    first = _create(api)
    assert first.status_code == 201, first.text
    again = _create(api)
    assert again.status_code == 200, again.text
    assert again.json()["id"] == first.json()["id"]
    with Session(api.engine) as session:
        assert session.scalar(select(func.count()).select_from(Investigation)) == 1
    other_provider = _create(api, provider="ollama")
    assert other_provider.status_code == 201
    assert other_provider.json()["id"] != first.json()["id"]


def test_reimport_at_another_commit_keeps_earlier_evidence_intact(
    api: Api, github: respx.MockRouter
) -> None:
    _mock_run(github)
    first = _create(api).json()["id"]
    api.work()
    before = api.client.get(f"/api/investigations/{first}").json()["evidence"]

    SHARED_CACHE._items.clear()
    github.routes.clear()
    github.route(host="testserver").pass_through()
    _mock_run(github, sha=OTHER_SHA)
    second = _create(api).json()["id"]
    api.work()

    after = api.client.get(f"/api/investigations/{first}").json()["evidence"]
    assert after == before
    with Session(api.engine) as session:
        snapshots = session.scalars(
            select(Repository.commit_sha).where(Repository.provider == "github")
        ).all()
        assert sorted(str(s) for s in snapshots) == sorted([SHA, OTHER_SHA])
        runs = session.scalars(select(WorkflowRun.head_sha)).all()
        assert sorted(runs) == sorted([SHA, OTHER_SHA])
        assert session.get_one(Investigation, uuid.UUID(second)).repository_id != (
            session.get_one(Investigation, uuid.UUID(first)).repository_id
        )


def test_without_a_token_the_log_can_be_pasted(anonymous: Api, github: respx.MockRouter) -> None:
    routes = _mock_run(github)
    created = _create(anonymous, log_text=LOG)
    assert created.status_code == 201, created.text
    assert not routes["logs"].called
    assert not routes["store"].called
    assert all("authorization" not in c.request.headers for c in github.calls)
    detail = anonymous.client.get(f"/api/investigations/{created.json()['id']}").json()
    assert detail["github_run"]["log_source"] == "pasted"


def test_without_a_token_or_paste_nothing_is_stored(
    anonymous: Api, github: respx.MockRouter
) -> None:
    _mock_run(github)
    github.get(f"{API}{LOGS_PATH}").mock(
        return_value=httpx.Response(403, json={"message": "Must have admin rights to Repository."})
    )
    response = _create(anonymous)
    assert response.status_code == 403
    assert "KENSA_GITHUB_TOKEN" in response.json()["detail"]
    with Session(anonymous.engine) as session:
        assert session.scalar(select(func.count()).select_from(Investigation)) == 0
        assert session.scalar(select(func.count()).select_from(Document)) == 0


@pytest.mark.parametrize(
    ("override", "status"),
    [
        ({"conclusion": "success"}, 409),
        ({"status": "in_progress", "conclusion": None}, 409),
        ({"repository": {"private": True}}, 422),
    ],
)
def test_runs_that_cannot_be_investigated_are_refused(
    api: Api, github: respx.MockRouter, override: dict[str, Any], status: int
) -> None:
    github.get(f"{API}{RUN_PATH}").mock(return_value=httpx.Response(200, json=run_json(**override)))
    assert _create(api).status_code == status


def test_expired_logs_are_reported(api: Api, github: respx.MockRouter) -> None:
    routes = _mock_run(github)
    routes["logs"].mock(return_value=httpx.Response(410, json={"message": "Gone"}))
    response = _create(api)
    assert response.status_code == 410
    assert "Paste the log" in response.json()["detail"]


def test_github_requests_must_name_a_valid_target(api: Api, github: respx.MockRouter) -> None:
    bad = {"owner": "../x", "repo": REPO, "run_id": RUN_ID}
    response = api.client.post("/api/investigations", json={"source": "github", "github": bad})
    assert response.status_code == 422
    missing = api.client.post("/api/investigations", json={"source": "github"})
    assert missing.status_code == 422
    assert not [c for c in github.calls if c.request.url.host != "testserver"]
