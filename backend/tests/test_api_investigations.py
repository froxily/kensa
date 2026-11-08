import re
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from kensa.agents.handler import make_investigate_handler, on_job_outcome
from kensa.app import create_app
from kensa.core.config import Settings
from kensa.db.models import Investigation, Workspace
from kensa.investigations.service import INVESTIGATE_JOB, RESUME_JOB
from kensa.jobs.worker import Worker

pytestmark = pytest.mark.db
FAKE_TOKEN = "ghp_" + "Qq1Ww2Ee3Rr4Tt5Yy6Uu7Ii8Oo9Pp0Aa1Ss2"


class Api:
    def __init__(self, client: TestClient, engine: Engine, settings: Settings) -> None:
        self.client, self.engine, self.settings = client, engine, settings

    def create(self, **body: Any) -> dict[str, Any]:
        response = self.client.post("/api/investigations", json=body)
        assert response.status_code == 201, response.text
        return dict(response.json())

    def work(self) -> None:
        handler = make_investigate_handler(self.settings)
        handlers = {INVESTIGATE_JOB: handler, RESUME_JOB: handler}
        Worker(self.engine, handlers, on_outcome=on_job_outcome).run_once()

    def detail(self, investigation_id: str) -> dict[str, Any]:
        response = self.client.get(f"/api/investigations/{investigation_id}")
        assert response.status_code == 200, response.text
        return dict(response.json())


@pytest.fixture
def api(db_engine: Engine, test_database_url: str) -> Iterator[Api]:
    settings = Settings(
        _env_file=None,
        database_url=test_database_url,
        worker_enabled=False,
        inference_provider="mock",
        embedding_provider="mock",
        max_request_bytes=200_000,
        stream_max_seconds=20,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        yield Api(client, app.state.engine, settings)


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def test_samples_are_listed_and_labelled_synthetic(api: Api) -> None:
    samples = api.client.get("/api/samples").json()
    assert [s["id"] for s in samples] == [
        "missing-env-var",
        "dependency-resolution",
        "db-connection",
    ]
    assert all(s["synthetic"] for s in samples)


def test_sample_runs_to_a_cited_report(api: Api) -> None:
    created = api.create(sample_id="missing-env-var")
    assert (created["status"], created["source"], created["provider"]) == (
        "queued",
        "sample",
        "mock",
    )
    api.work()

    detail = api.detail(created["id"])
    # M3: an established diagnosis pauses for a human decision on its remediation proposals.
    assert detail["status"] == "awaiting_approval"
    diagnosis = detail["diagnosis"]
    assert (diagnosis["category"], diagnosis["verification_status"]) == (
        "missing_env_var",
        "corroborated",
    )
    assert (diagnosis["evidence_complete"], diagnosis["diagnosis_attempts"]) == (True, 1)
    assert detail["decision"] is None
    assert detail["proposals"]
    assert {p["origin"] for p in detail["proposals"]} == {"template"}
    assert {p["status"] for p in detail["proposals"]} == {"proposed"}
    assert all(p["diff"] is None and p["validation_steps"] for p in detail["proposals"])
    first = detail["evidence"][0]
    assert first["label"] == "E1"
    assert first["source_type"] == "log"
    assert first["document_name"] == detail["documents"][0]["name"]
    assert detail["signatures"]

    document = detail["documents"][0]
    content = api.client.get(
        f"/api/investigations/{created['id']}/documents/{document['id']}"
    ).json()
    assert len(content["lines"]) == document["line_count"]
    valid = [c for c in diagnosis["citations"] if c["valid"]]
    assert valid
    for citation in valid:  # every accepted citation really is on the cited line
        assert _norm(citation["quote"]) in _norm(content["lines"][citation["line_number"] - 1])


def test_pasted_secrets_are_redacted_everywhere(api: Api) -> None:
    log = (
        f"##[group]Run deploy\nexport TOKEN={FAKE_TOKEN}\n"
        "Error: Missing required environment variable: API_URL\n"
    )
    created = api.create(log_text=log, document_name="deploy.log")
    api.work()
    detail = api.detail(created["id"])
    document = detail["documents"][0]
    assert document["redaction_count"] >= 1
    raw = api.client.get(f"/api/investigations/{created['id']}/documents/{document['id']}").text
    assert FAKE_TOKEN not in raw
    assert FAKE_TOKEN not in api.client.get(f"/api/investigations/{created['id']}").text


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"log_text": "x", "sample_id": "db-connection"},
        {"source": "sample", "log_text": "x"},
        {"log_text": "x", "provider": "openai"},
        {"log_text": "x", "unexpected": 1},
        {"log_text": "x", "title": "t" * 201},
        {"sample_id": "../../etc/passwd"},
        {"log_text": "   \n\t\n"},
    ],
)
def test_invalid_requests_are_rejected(api: Api, body: dict[str, Any]) -> None:
    assert api.client.post("/api/investigations", json=body).status_code == 422


def test_unknown_sample_is_404(api: Api) -> None:
    assert api.client.post("/api/investigations", json={"sample_id": "nope"}).status_code == 404


def test_oversized_body_is_rejected_before_parsing(api: Api) -> None:
    payload = b'{"log_text": "' + b"x" * 300_000 + b'"}'
    response = api.client.post(
        "/api/investigations", content=payload, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413


def test_list_is_newest_first_and_paginated(api: Api) -> None:
    ids = [api.create(log_text=f"error number {n}: boom")["id"] for n in range(3)]
    page = api.client.get("/api/investigations", params={"limit": 2}).json()
    assert page["total"] == 3
    assert [i["id"] for i in page["items"]] == ids[::-1][:2]
    rest = api.client.get("/api/investigations", params={"limit": 2, "offset": 2}).json()
    assert [i["id"] for i in rest["items"]] == [ids[0]]
    assert api.client.get("/api/investigations", params={"limit": 0}).status_code == 422


def test_other_workspaces_are_invisible(api: Api) -> None:
    other = uuid.uuid4()
    foreign = uuid.uuid4()
    with Session(api.engine) as session, session.begin():
        session.add(Workspace(id=other, name="someone-else"))
        session.flush()
        session.add(
            Investigation(
                id=foreign,
                workspace_id=other,
                title="secret",
                source="paste",
                provider="mock",
                status="failed",
            )
        )
    base = f"/api/investigations/{foreign}"
    assert api.client.get(base).status_code == 404
    assert api.client.get(f"{base}/events").status_code == 404
    assert api.client.get(f"{base}/stream").status_code == 404
    assert api.client.get(f"{base}/documents/{uuid.uuid4()}").status_code == 404
    assert api.client.post(f"{base}/retry", json={}).status_code == 404
    assert api.client.get("/api/investigations").json()["total"] == 0
    assert api.client.get(f"/api/investigations/{uuid.uuid4()}").status_code == 404
    assert api.client.get("/api/investigations/not-a-uuid").status_code == 422


def test_events_cursor(api: Api) -> None:
    created = api.create(sample_id="db-connection")
    api.work()
    events = api.client.get(f"/api/investigations/{created['id']}/events").json()
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    later = api.client.get(
        f"/api/investigations/{created['id']}/events", params={"after": 3}
    ).json()
    assert [e["seq"] for e in later] == [e["seq"] for e in events if e["seq"] > 3]


def test_stream_sends_events_status_and_end(api: Api) -> None:
    created = api.create(sample_id="dependency-resolution")
    api.work()
    url = f"/api/investigations/{created['id']}/stream"
    with api.client.stream("GET", url) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())
    assert body.count("event: agent_event") >= 8
    assert 'event: status\ndata: {"status": "awaiting_approval"}' in body
    assert body.rstrip().endswith("event: end\ndata: {}")

    with api.client.stream("GET", url, headers={"Last-Event-ID": "6"}) as response:
        resumed = "".join(response.iter_text())
    ids = [int(m) for m in re.findall(r"^id: (\d+)$", resumed, flags=re.MULTILINE)]
    assert ids
    assert min(ids) == 7


def test_retry_only_from_failed(api: Api) -> None:
    created = api.create(sample_id="missing-env-var")
    api.work()
    url = f"/api/investigations/{created['id']}/retry"
    assert api.client.post(url, json={}).status_code == 409
    with api.engine.begin() as conn:
        conn.execute(text("UPDATE investigations SET status = 'failed', error_code = 'x'"))
    retried = api.client.post(url, json={})
    assert retried.status_code == 200
    assert (retried.json()["status"], retried.json()["error_code"]) == ("queued", None)
    api.work()
    # The retried job finds the graph paused at the approval step and leaves it waiting.
    assert api.detail(created["id"])["status"] == "awaiting_approval"
