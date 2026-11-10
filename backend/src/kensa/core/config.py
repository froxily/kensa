"""Application settings, read from ``KENSA_*`` environment variables and the repo-root ``.env``."""

from functools import lru_cache
from ipaddress import ip_address
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/src/kensa/core/config.py -> repository root
REPO_ROOT = Path(__file__).resolve().parents[4]


Channel = Literal["signature", "fts", "vector"]


def _all_channels() -> list[Channel]:
    return ["signature", "fts", "vector"]


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KENSA_",
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # SecretStr keeps the password out of reprs and logs.
    database_url: SecretStr = SecretStr("postgresql+psycopg://kensa@127.0.0.1:5433/kensa")
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:5173", "http://localhost:5173"]
    )
    # Host headers the API answers (M5 security audit): anything else is refused, so a web page
    # that re-points its own domain at 127.0.0.1 (DNS rebinding) cannot reach the API.
    allowed_hosts: list[str] = Field(default_factory=lambda: ["127.0.0.1", "localhost"])

    inference_provider: Literal["ollama", "mock"] = "ollama"
    ollama_base_url: str = "http://127.0.0.1:11434"
    llm_model: str = Field(default="qwen3:4b-instruct-2507-q4_K_M", min_length=1, max_length=200)
    # Measured in the M0 benchmark on a 4 GB RTX 3050 (DECISIONS.md D-009): Ollama's automatic
    # placement left a third of the layers on the CPU, so requests ask for every layer on the GPU.
    llm_num_ctx: int = Field(default=8192, ge=512, le=32768)
    llm_num_gpu: int | None = Field(default=99, ge=0, le=999)
    llm_timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    health_timeout_seconds: float = Field(default=2.0, gt=0, le=10)

    # Embeddings and hybrid retrieval (M2). "mock" = deterministic hashing embedder (CI/tests);
    # "none" disables the vector channel. Measured in M2 (DECISIONS.md D-024): on the CPU the
    # embedder managed 0.8 chunks/s versus 41 on the GPU, so it uses Ollama's default (GPU)
    # placement; the two models cannot share 4 GB, so they run one after the other.
    embedding_provider: Literal["ollama", "mock", "none"] = "ollama"
    embedding_model: str = Field(default="qwen3-embedding:0.6b", min_length=1, max_length=100)
    embedding_num_gpu: int | None = Field(default=None, ge=0, le=999)
    retrieval_channels: list[Channel] = Field(default_factory=_all_channels)
    # Index corroborated investigations as "incident" documents for later retrieval. Off since
    # v1.1 (D-051): a model's earlier conclusion must not anchor a new diagnosis. Similar
    # failures are shown as history instead (fingerprints, D-053).
    index_incidents: bool = False
    # Show earlier failures as recurrences or similar failures (D-057). Experimental and
    # off by default: fingerprint version 3 met its precision targets on held-out data but
    # missed recall and similar-failure Recall@5 (eval/reports/v11-v4-history-test.md).
    # Fingerprints are still recorded either way, so turning it on needs no backfill.
    history_matching: bool = False

    # Agent workflow budgets (M3, DECISIONS.md D-028). Every run is bounded by all of them.
    # Diagnoses per run: the first plus verifier-requested retries.
    agent_max_diagnosis_attempts: int = Field(default=3, ge=1, le=5)
    # Targeted retrieval rounds after the first, when the evidence misses the failure lines.
    agent_max_retrieval_rounds: int = Field(default=2, ge=0, le=5)
    # Model calls per run (diagnoses plus the remediation planner).
    agent_max_llm_calls: int = Field(default=4, ge=1, le=10)
    # Wall-clock budget per job attempt; no new model call starts after it.
    agent_max_seconds: float = Field(default=900.0, gt=10, le=7200)
    # Ask the model for minimal file edits (validated, turned into diffs, never applied).
    remediation_diffs: bool = True

    # GitHub (M4, DECISIONS.md D-031): read-only, public repositories, https://api.github.com
    # only. Anonymous unless the owner sets a fine-grained, read-only personal access token,
    # which GitHub requires for downloading job logs. Never the GitHub CLI's login token.
    github_token: SecretStr | None = None
    github_timeout_seconds: float = Field(default=20.0, gt=1, le=120)
    # Largest job log Kensa downloads; longer logs keep their last 2 MB (the ingestion limit).
    github_max_log_bytes: int = Field(default=16_000_000, ge=100_000, le=64_000_000)
    # Repository files fetched per import besides the workflow file.
    github_max_files: int = Field(default=6, ge=0, le=20)

    # CI history (v1.1, D-052): manual, incremental syncs of tracked public repositories.
    # GitHub requests one sync may make (a 304 counts); the next sync continues where it stopped.
    history_request_budget: int = Field(default=300, ge=10, le=2000)
    # How far back the first sync of a newly tracked repository reads.
    history_default_days: int = Field(default=30, ge=1, le=400)

    # Change-aware investigation (v1.1, D-054): compare an imported run with the last comparable
    # successful run of its workflow. GitHub requests one comparison may make.
    change_analysis: bool = True
    change_request_budget: int = Field(default=8, ge=2, le=30)
    # Make suspected changes' hunks retrievable, citable evidence (False keeps only the notes).
    change_diff_evidence: bool = True

    # Background worker (in-process; DECISIONS.md D-006). Tests disable it and drive it directly.
    worker_enabled: bool = True
    worker_lease_seconds: float = Field(default=30.0, gt=1, le=600)
    worker_heartbeat_seconds: float = Field(default=10.0, gt=0.1, le=300)
    worker_poll_seconds: float = Field(default=1.0, gt=0.01, le=60)

    # Local observability (M5, D-034): OpenTelemetry spans to a JSONL file under this folder.
    # Nothing is exported over the network.
    telemetry_enabled: bool = True
    telemetry_dir: Path = REPO_ROOT / ".telemetry"

    # Requests larger than this are rejected before their body is read.
    max_request_bytes: int = Field(default=2_500_000, ge=1_000, le=50_000_000)
    # Live progress streams end after this long; the browser reconnects if still interested.
    stream_max_seconds: float = Field(default=600.0, gt=1, le=3600)

    @field_validator("github_token", mode="before")
    @classmethod
    def _blank_token_is_none(cls, value: object) -> object:
        """An empty ``KENSA_GITHUB_TOKEN=`` line means anonymous access, not an empty token."""
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return None
        return raw.strip() if isinstance(raw, str) else value

    @field_validator("ollama_base_url")
    @classmethod
    def _ollama_must_be_loopback(cls, value: str) -> str:
        """Inference is local-only: refuse any Ollama endpoint that is not on this machine."""
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("must be an http(s) URL")
        if parts.username or parts.password:
            raise ValueError("must not contain credentials")
        if not _is_loopback(parts.hostname):
            raise ValueError("must point at a loopback address (local-only inference)")
        return value.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
