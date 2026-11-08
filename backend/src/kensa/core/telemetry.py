"""Local observability (M5, DECISIONS.md D-034).

* Traces: OpenTelemetry spans written to a local JSONL file (``.telemetry/traces.jsonl``,
  git-ignored, rotated at a size cap). No network exporter is configured and no ``OTEL_*``
  variable can add one, so nothing leaves the machine.
* Spans: HTTP requests (FastAPI), database queries (SQLAlchemy), background jobs, agent graph
  nodes, model calls (with Ollama's load, prompt and generation timings and token counts),
  embeddings and GitHub requests. GitHub and Ollama calls are traced by hand instead of by the
  httpx instrumentation, which would record full URLs: signed log URLs must never reach a trace.
* Logs: every structured log line carries the current ``trace_id``/``span_id`` and the
  ``request_id`` of the HTTP request it belongs to, so logs and traces can be joined.
"""

import functools
import json
import re
import threading
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from structlog.types import EventDict, WrappedLogger

from kensa import __version__

tracer = trace.get_tracer("kensa")
MAX_TRACE_BYTES = 20_000_000
_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_provider: TracerProvider | None = None


def _record(span: ReadableSpan) -> dict[str, Any]:
    context = span.get_span_context()
    parent = span.parent
    start, end = span.start_time or 0, span.end_time or 0
    return {
        "name": span.name,
        "trace_id": f"{context.trace_id:032x}" if context else None,
        "span_id": f"{context.span_id:016x}" if context else None,
        "parent_id": f"{parent.span_id:016x}" if parent else None,
        "start": datetime.fromtimestamp(start / 1e9, UTC).isoformat(),
        "duration_ms": round((end - start) / 1e6, 3),
        "status": span.status.status_code.name,
        "attributes": {
            k: v if not isinstance(v, tuple) else list(v)
            for k, v in (span.attributes or {}).items()
        },
    }


class JsonlSpanExporter(SpanExporter):
    """Appends one JSON object per finished span to a local file; rotates once at a size cap."""

    def __init__(self, path: Path, max_bytes: int = MAX_TRACE_BYTES) -> None:
        self.path = path
        self.max_bytes = max_bytes
        self._lock = threading.Lock()

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        lines = "".join(json.dumps(_record(s), default=str) + "\n" for s in spans)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and self.path.stat().st_size > self.max_bytes:
                self.path.replace(self.path.with_suffix(".jsonl.1"))
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(lines)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


def configure_tracing(enabled: bool, directory: Path) -> TracerProvider | None:
    """Install the process-wide tracer provider once. Returns None when tracing is off."""
    global _provider
    if not enabled:
        return None
    if _provider is None:
        provider = TracerProvider(
            resource=Resource.create({"service.name": "kensa", "service.version": __version__})
        )
        provider.add_span_processor(
            BatchSpanProcessor(JsonlSpanExporter(directory / "traces.jsonl"))
        )
        trace.set_tracer_provider(provider)
        _provider = provider
    return _provider


def traced[**P, R](name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Run the function inside a span; attributes are added with ``set_span_attributes``."""

    def wrap(function: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(function)
        def inner(*args: P.args, **kwargs: P.kwargs) -> R:
            with tracer.start_as_current_span(name):
                return function(*args, **kwargs)

        return inner

    return wrap


def set_span_attributes(**attributes: str | int | float | bool | None) -> None:
    span = trace.get_current_span()
    for key, value in attributes.items():
        if value is not None:
            span.set_attribute(f"kensa.{key}", value)


def add_trace_ids(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    """structlog processor: join log lines to the current span."""
    context = trace.get_current_span().get_span_context()
    if context.is_valid:
        event_dict["trace_id"] = f"{context.trace_id:032x}"
        event_dict["span_id"] = f"{context.span_id:016x}"
    return event_dict


class RequestIdMiddleware:
    """Gives every HTTP request an id (the caller's ``X-Request-ID`` if well-formed), binds it to
    the logs and returns it in the response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        supplied = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode("latin-1")
        request_id = supplied if _REQUEST_ID.match(supplied) else uuid.uuid4().hex

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        with structlog.contextvars.bound_contextvars(request_id=request_id):
            await self.app(scope, receive, send_with_id)
