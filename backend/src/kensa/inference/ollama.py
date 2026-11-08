"""Ollama: availability probe and the structured-output provider.

Requests go straight to Ollama's HTTP API with httpx (DECISIONS.md D-017). Every request sends
the options measured in M0 (D-009): all layers on the GPU and a fixed context size.
"""

import time
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from kensa.core.telemetry import set_span_attributes, traced
from kensa.inference.base import (
    InferenceError,
    InferenceTimeoutError,
    MalformedOutputError,
    ModelMissingError,
    ModelUnavailableError,
    StructuredRequest,
    StructuredResult,
)

MAX_OUTPUT_TOKENS = 1024
REPAIR_PROMPT = (
    "Your previous reply did not match the required JSON schema ({count} problem(s); first: "
    "{first}). Reply again with only a JSON object that matches the schema exactly."
)


class OllamaStatus(BaseModel):
    status: Literal["ok", "unavailable", "model_missing", "error", "disabled"]
    model: str
    detail: str | None = None


class _TagModel(BaseModel):
    name: str


class _TagsResponse(BaseModel):
    models: list[_TagModel] = Field(default_factory=list)


def normalize_model_name(name: str) -> str:
    """Ollama treats an untagged name as ``:latest``."""
    return name if ":" in name else f"{name}:latest"


def probe_ollama(base_url: str, model: str, timeout: float) -> OllamaStatus:
    try:
        with httpx.Client(base_url=base_url, timeout=timeout, follow_redirects=False) as client:
            response = client.get("/api/tags")
    except httpx.TimeoutException:
        return OllamaStatus(status="unavailable", model=model, detail="timeout")
    except httpx.TransportError:
        return OllamaStatus(status="unavailable", model=model, detail="connection_failed")

    if response.status_code != httpx.codes.OK:
        return OllamaStatus(status="error", model=model, detail=f"http_{response.status_code}")
    try:
        tags = _TagsResponse.model_validate_json(response.content)
    except ValidationError:
        return OllamaStatus(status="error", model=model, detail="malformed_response")

    wanted = normalize_model_name(model)
    if any(normalize_model_name(tag.name) == wanted for tag in tags.models):
        return OllamaStatus(status="ok", model=model)
    return OllamaStatus(status="model_missing", model=model)


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        num_ctx: int,
        num_gpu: int | None,
        timeout_seconds: float,
        seed: int = 42,
    ) -> None:
        self.base_url = base_url
        self.model: str | None = model
        self.options: dict[str, Any] = {
            "temperature": 0,
            "seed": seed,
            "num_ctx": num_ctx,
            "num_predict": MAX_OUTPUT_TOKENS,
        }
        if num_gpu is not None:
            self.options["num_gpu"] = num_gpu
        self.timeout_seconds = timeout_seconds

    def _chat(
        self, client: httpx.Client, messages: list[dict[str, str]], schema: dict[str, Any]
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": schema,
            "options": self.options,
            "keep_alive": "10m",
        }
        try:
            response = client.post("/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            raise InferenceTimeoutError(f"no reply within {self.timeout_seconds:.0f}s") from exc
        except httpx.TransportError as exc:
            raise ModelUnavailableError("Ollama is not reachable") from exc
        if response.status_code == httpx.codes.NOT_FOUND:
            raise ModelMissingError(f"model '{self.model}' is not available in Ollama")
        if response.status_code >= 400:
            raise InferenceError(f"Ollama returned HTTP {response.status_code}")
        try:
            body = response.json()
        except ValueError as exc:
            raise InferenceError("Ollama returned a non-JSON response") from exc
        if not isinstance(body, dict):
            raise InferenceError("Ollama returned an unexpected response")
        return body

    @traced("llm.generate")
    def generate_structured[T: BaseModel](
        self, request: StructuredRequest[T]
    ) -> StructuredResult[T]:
        schema = request.schema.model_json_schema()
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        prompt_tokens = output_tokens = 0
        timings = dict.fromkeys(("load_ms", "prompt_eval_ms", "eval_ms", "total_ms"), 0.0)
        started = time.perf_counter()
        with httpx.Client(
            base_url=self.base_url, timeout=self.timeout_seconds, follow_redirects=False
        ) as client:
            for attempt in (1, 2):
                body = self._chat(client, messages, schema)
                prompt_tokens += int(body.get("prompt_eval_count") or 0)
                output_tokens += int(body.get("eval_count") or 0)
                for key, field_name in (
                    ("load_ms", "load_duration"),
                    ("prompt_eval_ms", "prompt_eval_duration"),
                    ("eval_ms", "eval_duration"),
                    ("total_ms", "total_duration"),
                ):
                    timings[key] += int(body.get(field_name) or 0) / 1e6
                message = body.get("message")
                content = str(message.get("content", "")) if isinstance(message, dict) else ""
                try:
                    value = request.schema.model_validate_json(content)
                except ValidationError as exc:
                    if attempt == 2:
                        raise MalformedOutputError(
                            f"invalid structured output after repair: {exc.error_count()} errors"
                        ) from exc
                    first = exc.errors()[0]
                    location = ".".join(str(p) for p in first["loc"]) or "(root)"
                    messages += [
                        {"role": "assistant", "content": content[:4000]},
                        {
                            "role": "user",
                            "content": REPAIR_PROMPT.format(
                                count=exc.error_count(), first=f"{location}: {first['msg']}"
                            ),
                        },
                    ]
                    continue
                duration_ms = int((time.perf_counter() - started) * 1000)
                rate = output_tokens / (timings["eval_ms"] / 1000) if timings["eval_ms"] else 0.0
                set_span_attributes(
                    task=request.task,
                    model=self.model,
                    num_ctx=int(self.options["num_ctx"]),
                    attempts=attempt,
                    prompt_tokens=prompt_tokens,
                    output_tokens=output_tokens,
                    duration_ms=duration_ms,
                    load_ms=round(timings["load_ms"], 1),
                    prompt_eval_ms=round(timings["prompt_eval_ms"], 1),
                    eval_ms=round(timings["eval_ms"], 1),
                    eval_tokens_per_s=round(rate, 1),
                )
                return StructuredResult(
                    value=value,
                    provider=self.name,
                    model=self.model,
                    prompt_tokens=prompt_tokens,
                    output_tokens=output_tokens,
                    duration_ms=duration_ms,
                    attempts=attempt,
                    timings={k: round(v, 1) for k, v in timings.items()},
                )
        raise AssertionError("unreachable")  # pragma: no cover
