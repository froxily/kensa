import json
import math

import httpx
import pytest
import respx

from kensa.inference.base import ModelMissingError, ModelUnavailableError
from kensa.inference.embeddings import QUERY_INSTRUCTION, HashingEmbedder, OllamaEmbedder

BASE = "http://127.0.0.1:11434"


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_hashing_embedder_is_deterministic_normalised_and_lexical() -> None:
    embedder = HashingEmbedder(256)
    a, b, c = embedder.embed_documents(
        ["DATABASE_URL is not set", "missing DATABASE_URL variable", "docker manifest unknown"]
    )
    assert a == embedder.embed_documents(["DATABASE_URL is not set"])[0]
    assert math.isclose(sum(v * v for v in a), 1.0, rel_tol=1e-9)
    assert _cosine(a, b) > _cosine(a, c)


def test_ollama_embedder_batches_and_requests_cpu_placement(respx_mock: respx.MockRouter) -> None:
    def reply(request: httpx.Request) -> httpx.Response:
        inputs = json.loads(request.content)["input"]
        return httpx.Response(200, json={"embeddings": [[3.0, 4.0] for _ in inputs]})

    route = respx_mock.post(f"{BASE}/api/embed").mock(side_effect=reply)
    embedder = OllamaEmbedder(
        BASE, "qwen3-embedding:0.6b", dimensions=2, num_gpu=0, timeout_seconds=5, batch_size=2
    )
    vectors = embedder.embed_documents(["a", "b", "c"])
    assert vectors == [[0.6, 0.8]] * 3  # normalised
    assert route.call_count == 2  # batches of 2
    sent = json.loads(route.calls[0].request.content)
    assert sent["options"] == {"num_gpu": 0}
    assert sent["truncate"] is True

    embedder.embed_query("why did it fail")
    query = json.loads(route.calls.last.request.content)["input"][0]
    assert query.startswith(QUERY_INSTRUCTION)


@pytest.mark.parametrize(
    ("mock", "error"),
    [
        ({"side_effect": httpx.ConnectError("down")}, ModelUnavailableError),
        ({"return_value": httpx.Response(404, json={"error": "not found"})}, ModelMissingError),
    ],
)
def test_ollama_embedder_errors(
    respx_mock: respx.MockRouter, mock: dict[str, object], error: type[Exception]
) -> None:
    respx_mock.post(f"{BASE}/api/embed").mock(**mock)  # type: ignore[arg-type]
    embedder = OllamaEmbedder(BASE, "m", dimensions=2, num_gpu=0, timeout_seconds=5)
    with pytest.raises(error):
        embedder.embed_documents(["x"])


def test_wrong_dimension_is_rejected(respx_mock: respx.MockRouter) -> None:
    respx_mock.post(f"{BASE}/api/embed").mock(
        return_value=httpx.Response(200, json={"embeddings": [[1.0, 2.0, 3.0]]})
    )
    embedder = OllamaEmbedder(BASE, "m", dimensions=2, num_gpu=None, timeout_seconds=5)
    with pytest.raises(Exception, match="dimension"):
        embedder.embed_query("x")
