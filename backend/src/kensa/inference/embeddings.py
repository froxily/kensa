"""Embeddings (M2). ``OllamaEmbedder`` runs ``qwen3-embedding:0.6b`` locally; ``HashingEmbedder``
is a deterministic, model-free stand-in for CI and tests (labelled ``mock`` everywhere)."""

import hashlib
import math
import re
from typing import Any, Protocol

import httpx

from kensa.core.telemetry import set_span_attributes, traced
from kensa.inference.base import (
    InferenceError,
    InferenceTimeoutError,
    ModelMissingError,
    ModelUnavailableError,
)

# Qwen3-Embedding is instruction-aware on the query side only (documents are embedded as-is).
QUERY_INSTRUCTION = (
    "Instruct: Given an excerpt of a failed CI job log, retrieve the log lines, workflow "
    "configuration, code and documentation that explain the failure\nQuery: "
)
MAX_EMBED_CHARS = 4000
_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]+|\d+")


class Embedder(Protocol):
    name: str
    model: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def _normalise(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class HashingEmbedder:
    """Feature-hashed bag of tokens: captures lexical overlap only. For CI and tests."""

    name = "mock"
    model = "hashing-v1"

    def __init__(self, dimensions: int = 1024) -> None:
        self.dimensions = dimensions

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _TOKEN.findall(text.lower()):
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dimensions
            vector[index] += 1.0 if digest[4] & 1 else -1.0
        return _normalise(vector)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class OllamaEmbedder:
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        dimensions: int,
        num_gpu: int | None,
        timeout_seconds: float,
        batch_size: int = 16,
    ) -> None:
        self.base_url, self.model, self.dimensions = base_url, model, dimensions
        self.options: dict[str, Any] = {} if num_gpu is None else {"num_gpu": num_gpu}
        self.timeout_seconds, self.batch_size = timeout_seconds, batch_size

    @traced("embed")
    def _embed(self, inputs: list[str]) -> list[list[float]]:
        payload = {
            "model": self.model,
            "input": [text[:MAX_EMBED_CHARS] for text in inputs],
            "truncate": True,
            "keep_alive": "10m",
            "options": self.options,
        }
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
                response = client.post("/api/embed", json=payload)
        except httpx.TimeoutException as exc:
            raise InferenceTimeoutError("embedding request timed out") from exc
        except httpx.TransportError as exc:
            raise ModelUnavailableError("Ollama is not reachable") from exc
        if response.status_code == httpx.codes.NOT_FOUND:
            raise ModelMissingError(f"embedding model '{self.model}' is not available")
        if response.status_code >= 400:
            raise InferenceError(f"Ollama returned HTTP {response.status_code}")
        body = response.json()
        set_span_attributes(
            model=self.model,
            inputs=len(inputs),
            load_ms=round(int(body.get("load_duration") or 0) / 1e6, 1),
            total_ms=round(int(body.get("total_duration") or 0) / 1e6, 1),
        )
        vectors = body.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(inputs):
            raise InferenceError("unexpected embedding response")
        if any(len(v) != self.dimensions for v in vectors):
            raise InferenceError(f"embedding dimension is not {self.dimensions}")
        return [_normalise([float(x) for x in v]) for v in vectors]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            vectors += self._embed(texts[start : start + self.batch_size])
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed([QUERY_INSTRUCTION + text])[0]
