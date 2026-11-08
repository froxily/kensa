"""M5 observability: local spans, no secrets in traces, Ollama timings, request ids."""

import json
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel
from sqlalchemy import Engine

from kensa.app import create_app
from kensa.core.config import Settings
from kensa.core.telemetry import JsonlSpanExporter, add_trace_ids, tracer
from kensa.github.client import ETagCache, GitHubClient
from kensa.inference.base import ChatMessage, StructuredRequest
from kensa.inference.mock import MockProvider
from kensa.inference.ollama import OllamaProvider
from tests.conftest import BACKEND_DIR
from tests.github_fixtures import (
    API,
    JOB_ID,
    LOG,
    LOGS_PATH,
    OWNER,
    REPO,
    SIGNATURE,
    STORE_HOST,
    STORE_URL,
)

_MEMORY = InMemorySpanExporter()


@pytest.fixture(scope="session", autouse=True)
def _provider() -> None:
    """One in-memory provider for the session (a process can install only one)."""
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(_MEMORY))
    trace.set_tracer_provider(provider)


@pytest.fixture
def spans() -> InMemorySpanExporter:
    _MEMORY.clear()
    return _MEMORY


def _attributes(items: tuple[ReadableSpan, ...]) -> str:
    return json.dumps([dict(s.attributes or {}) for s in items], default=str)


def test_spans_are_written_as_local_json_lines(tmp_path: Path) -> None:
    exporter = JsonlSpanExporter(tmp_path / "traces.jsonl", max_bytes=200)
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    local = provider.get_tracer("test")
    for index in range(5):
        with local.start_as_current_span("unit", attributes={"kensa.n": index}):
            pass
    lines = (tmp_path / "traces.jsonl").read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[-1])
    assert set(record) >= {"name", "trace_id", "span_id", "duration_ms", "status", "attributes"}
    assert record["name"] == "unit"
    assert (tmp_path / "traces.jsonl.1").exists()  # rotated at the size cap


def test_no_network_exporter_is_ever_configured() -> None:
    sources = (BACKEND_DIR / "src" / "kensa").rglob("*.py")
    text = "\n".join(p.read_text(encoding="utf-8") for p in sources).lower()
    assert "otlp" not in text
    assert "httpxclientinstrumentor" not in text  # full URLs would reach spans


def test_github_spans_never_carry_signed_urls(spans: InMemorySpanExporter) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{API}{LOGS_PATH}").mock(
            return_value=httpx.Response(302, headers={"location": STORE_URL})
        )
        router.get(host=STORE_HOST).mock(return_value=httpx.Response(200, content=LOG.encode()))
        with GitHubClient(cache=ETagCache()) as client:
            client.job_log(OWNER, REPO, JOB_ID)
    finished = spans.get_finished_spans()
    assert {s.name for s in finished} >= {"github.job_log", "github.log_download"}
    download = next(s for s in finished if s.name == "github.log_download")
    assert (download.attributes or {})["kensa.log_store"] == STORE_HOST
    assert SIGNATURE not in _attributes(finished)
    assert "sig=" not in _attributes(finished)


class Answer(BaseModel):
    text: str


def test_model_calls_record_ollama_timings(spans: InMemorySpanExporter) -> None:
    reply = {
        "message": {"content": '{"text": "ok"}'},
        "prompt_eval_count": 120,
        "eval_count": 40,
        "load_duration": 4_000_000_000,
        "prompt_eval_duration": 500_000_000,
        "eval_duration": 2_000_000_000,
        "total_duration": 6_600_000_000,
    }
    with respx.mock() as router:
        router.post("http://127.0.0.1:11434/api/chat").mock(
            return_value=httpx.Response(200, json=reply)
        )
        provider = OllamaProvider(
            "http://127.0.0.1:11434", "m", num_ctx=2048, num_gpu=99, timeout_seconds=5
        )
        request = StructuredRequest("diagnosis", Answer, (ChatMessage("user", "x"),))
        result = provider.generate_structured(request)
    assert result.timings == {
        "load_ms": 4000.0,
        "prompt_eval_ms": 500.0,
        "eval_ms": 2000.0,
        "total_ms": 6600.0,
    }
    (span,) = [s for s in spans.get_finished_spans() if s.name == "llm.generate"]
    attributes = span.attributes or {}
    assert attributes["kensa.load_ms"] == 4000.0
    assert attributes["kensa.eval_tokens_per_s"] == 20.0
    assert attributes["kensa.output_tokens"] == 40


@pytest.mark.db
def test_jobs_and_graph_nodes_are_traced(
    spans: InMemorySpanExporter, db_engine: Engine, test_database_url: str
) -> None:
    from tests.test_agent import _create, _worker

    _create(db_engine, provider="mock")
    _worker(db_engine, test_database_url, MockProvider()).run_once()
    names = {s.name for s in spans.get_finished_spans()}
    assert {"job.investigate", "investigation.run", "node.collect_evidence", "node.verify"} <= names
    job = next(s for s in spans.get_finished_spans() if s.name == "job.investigate")
    node = next(s for s in spans.get_finished_spans() if s.name == "node.verify")
    assert node.context.trace_id == job.context.trace_id  # one trace per job


def test_logs_carry_the_current_trace_id() -> None:
    with tracer.start_as_current_span("unit") as span:
        event = add_trace_ids(None, "info", {"event": "x"})
    assert event["trace_id"] == f"{span.get_span_context().trace_id:032x}"
    assert "trace_id" not in add_trace_ids(None, "info", {"event": "outside"})


def test_every_response_carries_a_request_id(test_database_url: str) -> None:
    settings = Settings(_env_file=None, database_url=test_database_url, worker_enabled=False)
    with TestClient(create_app(settings)) as client:
        echoed = client.get("/api/samples", headers={"X-Request-ID": "abc-123"})
        generated = client.get("/api/samples", headers={"X-Request-ID": "bad id!\n"})
    assert echoed.headers["x-request-id"] == "abc-123"
    assert len(generated.headers["x-request-id"]) == 32
