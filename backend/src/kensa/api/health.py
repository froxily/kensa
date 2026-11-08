"""Liveness and readiness endpoints."""

from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import Engine

from kensa import __version__
from kensa.core.config import Settings
from kensa.db.health import DatabaseStatus, probe_database
from kensa.inference.ollama import OllamaStatus, probe_ollama

router = APIRouter(prefix="/health", tags=["health"])

DatabaseProbe = Callable[[], DatabaseStatus]
OllamaProbe = Callable[[], OllamaStatus]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    inference_provider: Literal["ollama", "mock"]
    database: DatabaseStatus
    ollama: OllamaStatus


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_database_probe(request: Request) -> DatabaseProbe:
    engine: Engine = request.app.state.engine
    return lambda: probe_database(engine)


def get_ollama_probe(settings: Annotated[Settings, Depends(get_app_settings)]) -> OllamaProbe:
    if settings.inference_provider != "ollama":
        return lambda: OllamaStatus(status="disabled", model=settings.llm_model)
    return lambda: probe_ollama(
        settings.ollama_base_url, settings.llm_model, settings.health_timeout_seconds
    )


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("")
def ready(
    settings: Annotated[Settings, Depends(get_app_settings)],
    database_probe: Annotated[DatabaseProbe, Depends(get_database_probe)],
    ollama_probe: Annotated[OllamaProbe, Depends(get_ollama_probe)],
) -> HealthResponse:
    database = database_probe()
    ollama = ollama_probe()
    healthy = database.status == "ok" and ollama.status in {"ok", "disabled"}
    return HealthResponse(
        status="ok" if healthy else "degraded",
        version=__version__,
        inference_provider=settings.inference_provider,
        database=database,
        ollama=ollama,
    )
