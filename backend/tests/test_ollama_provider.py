import json

import httpx
import pytest
import respx
from pydantic import BaseModel

from kensa.inference.base import (
    ChatMessage,
    InferenceTimeoutError,
    MalformedOutputError,
    ModelMissingError,
    ModelUnavailableError,
    StructuredRequest,
)
from kensa.inference.mock import MockProvider
from kensa.inference.ollama import OllamaProvider

BASE = "http://127.0.0.1:11434"


class Answer(BaseModel):
    category: str
    confidence: float


REQUEST = StructuredRequest(
    task="t",
    schema=Answer,
    messages=(ChatMessage("user", "hi"),),
    hints={"mock_response": {"category": "x", "confidence": 0.5}},
)


def _provider() -> OllamaProvider:
    return OllamaProvider(
        BASE, "qwen3:4b-instruct-2507-q4_K_M", num_ctx=8192, num_gpu=99, timeout_seconds=5
    )


def _reply(content: str) -> httpx.Response:
    return httpx.Response(
        200, json={"message": {"content": content}, "prompt_eval_count": 10, "eval_count": 5}
    )


def test_valid_reply_and_request_options(respx_mock: respx.MockRouter) -> None:
    route = respx_mock.post(f"{BASE}/api/chat").mock(
        return_value=_reply('{"category": "docker", "confidence": 0.8}')
    )
    result = _provider().generate_structured(REQUEST)
    assert result.value == Answer(category="docker", confidence=0.8)
    assert (result.attempts, result.prompt_tokens, result.output_tokens) == (1, 10, 5)
    sent = json.loads(route.calls.last.request.content)
    assert sent["options"]["num_ctx"] == 8192
    assert sent["options"]["num_gpu"] == 99
    assert sent["options"]["temperature"] == 0
    assert sent["stream"] is False
    assert sent["format"]["properties"]["category"]["type"] == "string"


def test_one_repair_attempt_then_success(respx_mock: respx.MockRouter) -> None:
    route = respx_mock.post(f"{BASE}/api/chat").mock(
        side_effect=[
            _reply('{"category": "docker"}'),
            _reply('{"category": "docker", "confidence": 1}'),
        ]
    )
    result = _provider().generate_structured(REQUEST)
    assert result.attempts == 2
    assert result.prompt_tokens == 20
    repair = json.loads(route.calls.last.request.content)["messages"]
    assert repair[-2]["role"] == "assistant"
    assert "did not match the required JSON schema" in repair[-1]["content"]


def test_malformed_after_repair(respx_mock: respx.MockRouter) -> None:
    respx_mock.post(f"{BASE}/api/chat").mock(return_value=_reply("not json at all"))
    with pytest.raises(MalformedOutputError):
        _provider().generate_structured(REQUEST)


@pytest.mark.parametrize(
    ("mock", "error"),
    [
        ({"side_effect": httpx.ConnectError("refused")}, ModelUnavailableError),
        ({"side_effect": httpx.ReadTimeout("slow")}, InferenceTimeoutError),
        (
            {"return_value": httpx.Response(404, json={"error": "model not found"})},
            ModelMissingError,
        ),
    ],
)
def test_transport_failures_map_to_typed_errors(
    respx_mock: respx.MockRouter, mock: dict[str, object], error: type[Exception]
) -> None:
    respx_mock.post(f"{BASE}/api/chat").mock(**mock)  # type: ignore[arg-type]
    with pytest.raises(error):
        _provider().generate_structured(REQUEST)


def test_retryability_of_errors() -> None:
    assert ModelUnavailableError.retryable
    assert InferenceTimeoutError.retryable
    assert not ModelMissingError.retryable
    assert not MalformedOutputError.retryable


def test_mock_provider_returns_hinted_response() -> None:
    result = MockProvider().generate_structured(REQUEST)
    assert result.value == Answer(category="x", confidence=0.5)
    assert result.provider == "mock"
    with pytest.raises(MalformedOutputError):
        MockProvider().generate_structured(
            StructuredRequest(task="t", schema=Answer, messages=(), hints={})
        )
