"""The inference seam. Everything that talks to a model goes through ``InferenceProvider``."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel


class InferenceError(Exception):
    """Base class; ``code`` is stable and user-facing, ``retryable`` drives the job queue."""

    code = "inference_error"
    retryable = True


class ModelUnavailableError(InferenceError):
    code = "model_unavailable"


class InferenceTimeoutError(InferenceError):
    code = "inference_timeout"


class ModelMissingError(InferenceError):
    code = "model_missing"
    retryable = False


class MalformedOutputError(InferenceError):
    """The model's reply did not match the schema, even after one repair attempt."""

    code = "malformed_output"
    retryable = False


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class StructuredRequest[T: BaseModel]:
    task: str
    schema: type[T]
    messages: tuple[ChatMessage, ...]
    # Deterministic context for the mock provider. Never sent to a model.
    hints: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StructuredResult[T: BaseModel]:
    value: T
    provider: str
    model: str | None
    prompt_tokens: int | None
    output_tokens: int | None
    duration_ms: int
    attempts: int
    # Ollama's own timings, summed over attempts (ms): load, prompt_eval, eval, total.
    timings: Mapping[str, float] = field(default_factory=dict)


class InferenceProvider(Protocol):
    name: str
    model: str | None

    def generate_structured[T: BaseModel](
        self, request: StructuredRequest[T]
    ) -> StructuredResult[T]: ...
