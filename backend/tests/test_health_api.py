from typing import Literal

from fastapi.testclient import TestClient

from kensa.api.health import DatabaseProbe, OllamaProbe, get_database_probe, get_ollama_probe
from kensa.app import create_app
from kensa.core.config import Settings
from kensa.db.health import DatabaseStatus
from kensa.inference.ollama import OllamaStatus

MODEL = "qwen3:4b-instruct-2507-q4_K_M"
DB_OK = DatabaseStatus(status="ok", pgvector_version="0.8.7")
DB_DOWN = DatabaseStatus(status="unavailable", detail="connection_failed")
OLLAMA_OK = OllamaStatus(status="ok", model=MODEL)


def _client(
    db: DatabaseStatus,
    ollama: OllamaStatus | None = None,
    inference_provider: Literal["ollama", "mock"] = "ollama",
) -> TestClient:
    app = create_app(
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://u:s3cret-pw@127.0.0.1:5433/db",
            inference_provider=inference_provider,
        )
    )

    def database_probe() -> DatabaseProbe:
        return lambda: db

    app.dependency_overrides[get_database_probe] = database_probe
    if ollama is not None:

        def ollama_probe() -> OllamaProbe:
            return lambda: ollama

        app.dependency_overrides[get_ollama_probe] = ollama_probe
    return TestClient(app)


def test_live() -> None:
    response = _client(DB_OK, OLLAMA_OK).get("/api/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_ready_ok() -> None:
    response = _client(DB_OK, OLLAMA_OK).get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"]["pgvector_version"] == "0.8.7"
    assert body["ollama"]["status"] == "ok"
    assert body["inference_provider"] == "ollama"


def test_degraded_when_database_down() -> None:
    body = _client(DB_DOWN, OLLAMA_OK).get("/api/health").json()
    assert body["status"] == "degraded"
    assert body["database"] == {
        "status": "unavailable",
        "pgvector_version": None,
        "detail": "connection_failed",
    }


def test_degraded_when_model_missing() -> None:
    missing = OllamaStatus(status="model_missing", model=MODEL)
    body = _client(DB_OK, missing).get("/api/health").json()
    assert body["status"] == "degraded"
    assert body["ollama"]["status"] == "model_missing"


def test_mock_provider_skips_ollama() -> None:
    body = _client(DB_OK, inference_provider="mock").get("/api/health").json()
    assert body["status"] == "ok"
    assert body["ollama"]["status"] == "disabled"


def test_response_never_leaks_database_url() -> None:
    response = _client(DB_DOWN, OLLAMA_OK).get("/api/health")
    assert "s3cret-pw" not in response.text
    assert "5433" not in response.text


def test_cors_allows_only_configured_origins() -> None:
    client = _client(DB_OK, OLLAMA_OK)
    allowed = client.get("/api/health/live", headers={"Origin": "http://127.0.0.1:5173"})
    assert allowed.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"
    denied = client.get("/api/health/live", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in denied.headers
