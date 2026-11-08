"""Builds the provider an investigation asked for."""

from kensa.core.config import Settings
from kensa.db.models import EMBEDDING_DIM
from kensa.inference.base import InferenceProvider
from kensa.inference.embeddings import Embedder, HashingEmbedder, OllamaEmbedder
from kensa.inference.mock import MockProvider
from kensa.inference.ollama import OllamaProvider


def embedder_for(settings: Settings) -> Embedder | None:
    if settings.embedding_provider == "none":
        return None
    if settings.embedding_provider == "mock":
        return HashingEmbedder(EMBEDDING_DIM)
    return OllamaEmbedder(
        settings.ollama_base_url,
        settings.embedding_model,
        dimensions=EMBEDDING_DIM,
        num_gpu=settings.embedding_num_gpu,
        timeout_seconds=settings.llm_timeout_seconds,
    )


def provider_for(name: str, settings: Settings) -> InferenceProvider:
    if name == "mock":
        return MockProvider()
    if name == "ollama":
        return OllamaProvider(
            settings.ollama_base_url,
            settings.llm_model,
            num_ctx=settings.llm_num_ctx,
            num_gpu=settings.llm_num_gpu,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    raise ValueError(f"unknown inference provider '{name}'")
