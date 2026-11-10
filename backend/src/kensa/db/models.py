"""ORM models. Every tenant-owned table carries ``workspace_id`` (DECISIONS.md D-011).

String columns with a fixed vocabulary use CHECK constraints instead of PostgreSQL enums, so
adding a value is a one-line migration.
"""

import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from kensa.db.base import Base

# qwen3-embedding:0.6b produces 1024-dimensional vectors; a different model needs a migration.
EMBEDDING_DIM = 1024

# Seeded by the baseline migration; the single local operator works in this workspace.
DEFAULT_WORKSPACE_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

# v1.1: "diff" holds the hunks of a change correlated with a failure (D-054).
SOURCE_TYPES = ("log", "workflow_yaml", "code", "doc", "incident", "kb", "diff")
INVESTIGATION_SOURCES = ("paste", "upload", "sample", "github")
INVESTIGATION_STATUSES = ("queued", "running", "awaiting_approval", "completed", "failed")
PROVIDERS = ("ollama", "mock")
# M5.1 (D-040): root-cause statuses; evidence validity is reported separately by the citations.
VERIFICATION_STATUSES = ("corroborated", "plausible", "conflicting", "not_established")
EVENT_TYPES = ("started", "completed", "failed", "info")
JOB_STATUSES = ("queued", "running", "succeeded", "dead")
# "withdrawn": marked unsafe or non-actionable after the fact; kept for the audit trail (M5).
PROPOSAL_STATUSES = ("proposed", "approved", "rejected", "withdrawn")
PROPOSAL_ORIGINS = ("model", "template")
DECISIONS = ("approved", "rejected")
# v1.1 (D-051, D-052): where a history row came from. Analytics shows real observations by
# default and keeps fixtures loaded for evaluation or the replay apart.
DATA_ORIGINS = ("github_live", "eval_synthetic")
BATCH_STATUSES = ("running", "succeeded", "partial", "rate_limited", "failed")
DQ_SEVERITIES = ("info", "warning", "error")
PURGE_ACTIONS = ("forget_repository", "retention")
FINGERPRINT_ROLES = ("primary", "secondary")
# D-051: "human_confirmed" now; v1.3 adds the outcome of a later CI run.
RESOLUTION_PROVENANCE = ("human_confirmed",)
CHANGE_COMPARABILITY = (
    "comparable",
    "partially_comparable",
    "incomparable",
    "identical",
    "no_baseline",
    "history_unavailable",
)
SUSPECT_STATUSES = ("correlated", "weak")  # never "cause" (D-054)
ANALYTICS_SOURCES = ("ci", "investigation")
# Real observations (github_live, pasted) and everything else, kept apart (D-051).
ANALYTICS_ORIGINS = ("github_live", "pasted", "sample", "eval_synthetic", "replay")
CHANGE_KINDS = (
    "workflow",
    "dependency_manifest",
    "lockfile",
    "build_config",
    "env_declaration",
    "source",
    "test",
    "docs",
    "other",
    "runner_image",
)


FINGERPRINT_KINDS = ("exact", "approximate")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _workspace_fk() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = _created_at()


class Repository(Base):
    """A code repository whose files are indexed as context (local in M2; GitHub in M4).

    A GitHub repository is stored once per commit (``commit_sha``): a snapshot of the files a
    run executed. Evidence of an investigation therefore never changes when the same repository
    is imported again at another commit (DECISIONS.md D-033)."""

    __tablename__ = "repositories"
    __table_args__ = (
        CheckConstraint(_in("provider", ("local", "github")), name="provider"),
        CheckConstraint("(provider = 'github') = (commit_sha IS NOT NULL)", name="github_commit"),
        UniqueConstraint(
            "workspace_id",
            "provider",
            "name",
            "commit_sha",
            name="uq_repositories_name",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    provider: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(200))
    commit_sha: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = _created_at()


class Investigation(Base):
    __tablename__ = "investigations"
    __table_args__ = (
        CheckConstraint(_in("source", INVESTIGATION_SOURCES), name="source"),
        CheckConstraint(_in("status", INVESTIGATION_STATUSES), name="status"),
        CheckConstraint(_in("provider", PROVIDERS), name="provider"),
        Index("ix_investigations_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repositories.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), server_default="queued")
    provider: Mapped[str] = mapped_column(String(16))
    model: Mapped[str | None] = mapped_column(String(200))
    rule_category: Mapped[str | None] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(_in("source_type", SOURCE_TYPES), name="source_type"),
        # One identity per scope (DECISIONS.md D-022):
        # an investigation's log is unique by content, ...
        Index(
            "uq_documents_investigation_content",
            "workspace_id",
            "investigation_id",
            "source_type",
            "content_hash",
            unique=True,
            postgresql_where=text("investigation_id IS NOT NULL"),
        ),
        # ... a repository file by its path (re-indexing replaces it), ...
        Index(
            "uq_documents_repository_path",
            "workspace_id",
            "repository_id",
            "name",
            unique=True,
            postgresql_where=text("investigation_id IS NULL AND repository_id IS NOT NULL"),
        ),
        # ... and workspace knowledge (kb notes, past incidents) by its name.
        Index(
            "uq_documents_workspace_name",
            "workspace_id",
            "source_type",
            "name",
            unique=True,
            postgresql_where=text("investigation_id IS NULL AND repository_id IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(Integer)
    line_count: Mapped[int] = mapped_column(Integer)
    redaction_count: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = _created_at()


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "ordinal"),
        CheckConstraint("start_line >= 1 AND end_line >= start_line", name="line_range"),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    step_name: Mapped[str | None] = mapped_column(String(300))
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    # 'simple' keeps code tokens (ERESOLVE, OperationalError) unstemmed.
    tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple'::regconfig, content)", persisted=True),
        deferred=True,
    )
    # Filled by the indexing step (M2); NULL until embedded or when embeddings are disabled.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), deferred=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100))


class ErrorSignature(Base):
    __tablename__ = "error_signatures"
    __table_args__ = (Index("ix_error_signatures_lookup", "workspace_id", "kind", "value"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chunks.id", ondelete="SET NULL"), index=True
    )
    line_number: Mapped[int] = mapped_column(Integer)
    rule_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32))
    value: Mapped[str] = mapped_column(String(300))
    category_hint: Mapped[str | None] = mapped_column(String(32))
    weight: Mapped[int] = mapped_column(Integer)
    excerpt: Mapped[str] = mapped_column(String(500))


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint("investigation_id", "chunk_id"),
        UniqueConstraint("investigation_id", "label", name="uq_evidence_label"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(8))
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    channels: Mapped[list[str]] = mapped_column(ARRAY(Text))


class Diagnosis(Base):
    __tablename__ = "diagnoses"
    __table_args__ = (
        CheckConstraint(_in("verification_status", VERIFICATION_STATUSES), name="verification"),
        CheckConstraint(_in("provider", PROVIDERS), name="provider"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), unique=True
    )
    category: Mapped[str] = mapped_column(String(32))
    rule_category: Mapped[str | None] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    root_cause: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    uncertainty: Mapped[str] = mapped_column(Text)
    recommended_fixes: Mapped[list[str]] = mapped_column(ARRAY(Text))
    verification_status: Mapped[str] = mapped_column(String(16))
    verification_notes: Mapped[list[str]] = mapped_column(ARRAY(Text))
    provider: Mapped[str] = mapped_column(String(16))
    model: Mapped[str | None] = mapped_column(String(200))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    # M3: False when the log did not show the failure and Kensa abstained; NULL before M3.
    evidence_complete: Mapped[bool | None] = mapped_column(Boolean)
    # M3: diagnoses requested by the verifier loop (1 = accepted at the first attempt).
    diagnosis_attempts: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = _created_at()


class Citation(Base):
    __tablename__ = "citations"
    __table_args__ = (
        UniqueConstraint("diagnosis_id", "ordinal"),
        # A citation is either valid with no reason, or rejected with one. Never both (M3).
        CheckConstraint(
            "(valid AND rejection_reason IS NULL) OR (NOT valid AND rejection_reason IS NOT NULL)",
            name="valid_reason",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    diagnosis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("diagnoses.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    evidence_label: Mapped[str] = mapped_column(String(8))
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chunks.id", ondelete="SET NULL"))
    line_number: Mapped[int] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text)
    valid: Mapped[bool] = mapped_column(Boolean)
    rejection_reason: Mapped[str | None] = mapped_column(String(32))


class AgentEvent(Base):
    __tablename__ = "agent_events"
    __table_args__ = (
        UniqueConstraint("investigation_id", "seq"),
        CheckConstraint(_in("event_type", EVENT_TYPES), name="event_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE")
    )
    seq: Mapped[int] = mapped_column(Integer)
    attempt: Mapped[int] = mapped_column(Integer)
    node: Mapped[str] = mapped_column(String(32))
    event_type: Mapped[str] = mapped_column(String(16))
    summary: Mapped[str] = mapped_column(String(500))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created_at()


class RemediationProposal(Base):
    """A read-only remediation proposal (M3). Approving it records a decision; Kensa never
    applies it. ``diff`` is computed by Kensa from a validated edit, never taken from a model."""

    __tablename__ = "remediation_proposals"
    __table_args__ = (
        UniqueConstraint("investigation_id", "ordinal"),
        CheckConstraint(_in("status", PROPOSAL_STATUSES), name="status"),
        CheckConstraint(_in("origin", PROPOSAL_ORIGINS), name="origin"),
        CheckConstraint(
            "(status = 'withdrawn') = (withdrawn_reason IS NOT NULL)", name="withdrawn_reason"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text, server_default="")
    origin: Mapped[str] = mapped_column(String(16))
    target_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    target_path: Mapped[str | None] = mapped_column(String(255))
    diff: Mapped[str | None] = mapped_column(Text)
    risks: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    validation_steps: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    flags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    status: Mapped[str] = mapped_column(String(16), server_default="proposed")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_reason: Mapped[str | None] = mapped_column(Text)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


class ApprovalDecision(Base):
    """The operator's decision on an investigation's proposals. At most one per investigation,
    so a repeated or concurrent request can never record a second, different decision."""

    __tablename__ = "approval_decisions"
    __table_args__ = (CheckConstraint(_in("decision", DECISIONS), name="decision"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), unique=True
    )
    decision: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = _created_at()


class WorkflowRun(Base):
    """The GitHub Actions run and failed job an investigation was imported from (M4)."""

    __tablename__ = "workflow_runs"
    __table_args__ = (
        CheckConstraint(_in("log_source", ("github", "pasted")), name="log_source"),
        # v1.1: finds an earlier import of the same job, and every investigation of a repository
        # (Forget repository).
        Index("ix_workflow_runs_run", "workspace_id", "owner", "repo", "run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), unique=True
    )
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repositories.id", ondelete="SET NULL"), index=True
    )
    owner: Mapped[str] = mapped_column(String(100))
    repo: Mapped[str] = mapped_column(String(100))
    run_id: Mapped[int] = mapped_column(BigInteger)
    run_number: Mapped[int] = mapped_column(Integer)
    run_attempt: Mapped[int] = mapped_column(Integer)
    workflow_name: Mapped[str] = mapped_column(String(300))
    workflow_path: Mapped[str] = mapped_column(String(300))
    event: Mapped[str] = mapped_column(String(50))
    head_branch: Mapped[str | None] = mapped_column(String(300))
    head_sha: Mapped[str] = mapped_column(String(40))
    conclusion: Mapped[str | None] = mapped_column(String(32))
    html_url: Mapped[str] = mapped_column(String(500))
    job_id: Mapped[int] = mapped_column(BigInteger)
    job_name: Mapped[str] = mapped_column(String(200))
    job_html_url: Mapped[str] = mapped_column(String(500))
    failed_steps: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    log_source: Mapped[str] = mapped_column(String(16))
    log_dropped_lines: Mapped[int] = mapped_column(Integer, server_default="0")
    files_fetched: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    files_missing: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    created_at: Mapped[datetime] = _created_at()


class Job(Base):
    """Leased work item (DECISIONS.md D-006). See ``kensa.jobs.queue`` for the protocol."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(_in("status", JOB_STATUSES), name="status"),
        CheckConstraint("attempts >= 0 AND max_attempts >= 1", name="attempts"),
        Index("ix_jobs_claim", "status", "run_after"),
        # At most one queued or running job per investigation.
        Index(
            "uq_jobs_active_investigation",
            "investigation_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    kind: Mapped[str] = mapped_column(String(32))
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE")
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    status: Mapped[str] = mapped_column(String(16), server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, server_default="3")
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    lease_owner: Mapped[str | None] = mapped_column(String(100))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --------------------------------------------------------------------- v1.1: CI history ---


class TrackedRepository(Base):
    """A public GitHub repository whose workflow history Kensa keeps (v1.1, D-052).

    ``sync_state`` holds the incremental cursor: the date up to which runs are complete, an
    unfinished listing window, and runs that were still in progress at the last sync."""

    __tablename__ = "tracked_repositories"
    __table_args__ = (
        UniqueConstraint("workspace_id", "owner", "repo", name="uq_tracked_repositories_name"),
        CheckConstraint("history_days BETWEEN 1 AND 400", name="history_days"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    owner: Mapped[str] = mapped_column(String(100))
    repo: Mapped[str] = mapped_column(String(100))
    default_branch: Mapped[str | None] = mapped_column(String(300))
    history_days: Mapped[int] = mapped_column(Integer, server_default="30")
    sync_state: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    added_at: Mapped[datetime] = _created_at()
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EtlBatch(Base):
    """One incremental load: what it read, what it changed, and how far it got."""

    __tablename__ = "etl_batches"
    __table_args__ = (
        CheckConstraint(_in("status", BATCH_STATUSES), name="status"),
        Index("ix_etl_batches_repository_started", "tracked_repository_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    tracked_repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tracked_repositories.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), server_default="running")
    started_at: Mapped[datetime] = _created_at()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    watermark_before: Mapped[str | None] = mapped_column(String(40))
    watermark_after: Mapped[str | None] = mapped_column(String(40))
    counts: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    requests_used: Mapped[int] = mapped_column(Integer, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(64))
    message: Mapped[str | None] = mapped_column(String(300))


class CiRun(Base):
    """One attempt of a workflow run, as GitHub reported it. Natural key: run id + attempt."""

    __tablename__ = "ci_runs"
    __table_args__ = (
        UniqueConstraint(
            "tracked_repository_id", "run_id", "run_attempt", name="uq_ci_runs_attempt"
        ),
        CheckConstraint(_in("data_origin", DATA_ORIGINS), name="data_origin"),
        CheckConstraint("run_attempt >= 1", name="run_attempt"),
        Index(
            "ix_ci_runs_workflow",
            "tracked_repository_id",
            "workflow_id",
            "head_branch",
            "gh_created_at",
        ),
        Index("ix_ci_runs_sha", "tracked_repository_id", "head_sha"),
        Index("ix_ci_runs_workspace_created", "workspace_id", "gh_created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    tracked_repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tracked_repositories.id", ondelete="CASCADE")
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("etl_batches.id", ondelete="SET NULL")
    )
    run_id: Mapped[int] = mapped_column(BigInteger)
    run_attempt: Mapped[int] = mapped_column(Integer)
    run_number: Mapped[int] = mapped_column(Integer)
    workflow_id: Mapped[int] = mapped_column(BigInteger)
    workflow_path: Mapped[str] = mapped_column(String(300))
    workflow_name: Mapped[str] = mapped_column(String(300))
    event: Mapped[str] = mapped_column(String(50))
    head_branch: Mapped[str | None] = mapped_column(String(300))
    head_sha: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(32))
    conclusion: Mapped[str | None] = mapped_column(String(32))
    gh_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    run_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gh_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    jobs_synced: Mapped[bool] = mapped_column(Boolean, server_default="false")
    data_origin: Mapped[str] = mapped_column(String(16), server_default="github_live")
    ingested_at: Mapped[datetime] = _created_at()


class CiJob(Base):
    """A job of one run attempt. GitHub gives every attempt's jobs their own ids."""

    __tablename__ = "ci_jobs"
    __table_args__ = (UniqueConstraint("workspace_id", "job_id", name="uq_ci_jobs_job"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    ci_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ci_runs.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(32))
    conclusion: Mapped[str | None] = mapped_column(String(32))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    labels: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    steps: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))


class DqFinding(Base):
    """A data-quality problem found by a check; resolved when a later check no longer finds it."""

    __tablename__ = "dq_findings"
    __table_args__ = (
        UniqueConstraint("workspace_id", "check", "entity_key", name="uq_dq_findings_entity"),
        CheckConstraint(_in("severity", DQ_SEVERITIES), name="severity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    tracked_repository_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tracked_repositories.id", ondelete="CASCADE"), index=True
    )
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    check: Mapped[str] = mapped_column(String(48))
    severity: Mapped[str] = mapped_column(String(16))
    entity_key: Mapped[str] = mapped_column(String(300))
    detail: Mapped[str] = mapped_column(String(500))
    first_seen: Mapped[datetime] = _created_at()
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PurgeAudit(Base):
    """That a purge happened, and how much it removed. It names nothing it deleted: the scope is
    a SHA-256 digest (of ``owner/repo``, or of the retention cutoff)."""

    __tablename__ = "purge_audits"
    __table_args__ = (CheckConstraint(_in("action", PURGE_ACTIONS), name="action"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    action: Mapped[str] = mapped_column(String(32))
    scope_digest: Mapped[str] = mapped_column(String(64))
    counts: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = _created_at()


# --------------------------------------------------- v1.1: failure fingerprints (D-053) ---


class FailureFingerprint(Base):
    """A kind of failure, named by a deterministic hash of rule-derived facts (see
    ``kensa.analysis.fingerprint``). Never derived from model output."""

    __tablename__ = "failure_fingerprints"
    __table_args__ = (
        UniqueConstraint("workspace_id", "version", "hash", name="uq_failure_fingerprints_hash"),
        Index("ix_failure_fingerprints_tsv", "tsv", postgresql_using="gin"),
        CheckConstraint(_in("kind", FINGERPRINT_KINDS), name="kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    version: Mapped[int] = mapped_column(Integer)
    hash: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(32))
    rule_id: Mapped[str] = mapped_column(String(100))
    subject: Mapped[str] = mapped_column(String(200))
    template: Mapped[str] = mapped_column(String(240))
    # exact: may claim a recurrence; approximate: only finds similar failures (D-057).
    kind: Mapped[str] = mapped_column(String(16), server_default="exact")
    tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple'::regconfig, subject || ' ' || template)", persisted=True),
    )
    created_at: Mapped[datetime] = _created_at()


class InvestigationFingerprint(Base):
    __tablename__ = "investigation_fingerprints"
    __table_args__ = (
        UniqueConstraint(
            "investigation_id", "fingerprint_id", name="uq_investigation_fingerprints_link"
        ),
        CheckConstraint(_in("role", FINGERPRINT_ROLES), name="role"),
        Index("ix_investigation_fingerprints_fingerprint", "fingerprint_id", "role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    fingerprint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("failure_fingerprints.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = _created_at()


class Resolution(Base):
    """How a failure was resolved, as the operator confirmed it (D-051: ``human_confirmed``).
    Shown with similar failures later; it never changes a diagnosis or its status."""

    __tablename__ = "resolutions"
    __table_args__ = (CheckConstraint(_in("provenance", RESOLUTION_PROVENANCE), name="provenance"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    provenance: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = _created_at()
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------- v1.1: change-aware investigation (D-054) ---


class ChangeAnalysisRecord(Base):
    """How a failed run compares with an earlier successful run, factor by factor."""

    __tablename__ = "change_analyses"
    __table_args__ = (
        CheckConstraint(_in("comparability", CHANGE_COMPARABILITY), name="comparability"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), unique=True
    )
    comparability: Mapped[str] = mapped_column(String(32))
    reasons: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    factors: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    unverified: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    baseline_run_id: Mapped[int | None] = mapped_column(BigInteger)
    baseline_sha: Mapped[str | None] = mapped_column(String(40))
    failed_sha: Mapped[str] = mapped_column(String(40))
    compare_status: Mapped[str | None] = mapped_column(String(20))
    commits: Mapped[int] = mapped_column(Integer, server_default="0")
    files: Mapped[int] = mapped_column(Integer, server_default="0")
    truncated: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = _created_at()


class ChangeSuspect(Base):
    """A change correlated with the failure. Its status is ``correlated`` or ``weak``; the
    CHECK constraint has no value meaning "the cause" (D-054)."""

    __tablename__ = "change_suspects"
    __table_args__ = (
        UniqueConstraint("analysis_id", "rank", name="uq_change_suspects_rank"),
        CheckConstraint(_in("status", SUSPECT_STATUSES), name="status"),
        CheckConstraint(_in("change_kind", CHANGE_KINDS), name="change_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("change_analyses.id", ondelete="CASCADE"), index=True
    )
    rank: Mapped[int] = mapped_column(Integer)
    path: Mapped[str] = mapped_column(String(500))
    change_kind: Mapped[str] = mapped_column(String(32))
    score: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16))
    signals: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )


# ----------------------------------------------------------- v1.1: analytics (D-055) ---


class AnalyticsDaily(Base):
    """Daily counts per repository, workflow, category and data origin, recomputed per day from
    CI history and investigations (``kensa.analytics.refresh``). Counts only: nothing here can
    rebuild a log or a diagnosis."""

    __tablename__ = "analytics_daily"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "day",
            "source",
            "repository",
            "workflow",
            "category",
            "data_origin",
            name="uq_analytics_daily_key",
        ),
        CheckConstraint(_in("source", ANALYTICS_SOURCES), name="source"),
        CheckConstraint(_in("data_origin", ANALYTICS_ORIGINS), name="data_origin"),
        Index("ix_analytics_daily_workspace_day", "workspace_id", "day"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    day: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(16))
    repository: Mapped[str] = mapped_column(String(201))
    workflow: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(32))
    data_origin: Mapped[str] = mapped_column(String(16))
    runs: Mapped[int] = mapped_column(Integer, server_default="0")
    failed_runs: Mapped[int] = mapped_column(Integer, server_default="0")
    investigations: Mapped[int] = mapped_column(Integer, server_default="0")
    corroborated: Mapped[int] = mapped_column(Integer, server_default="0")
    latency_p50_ms: Mapped[int | None] = mapped_column(Integer)
    latency_p95_ms: Mapped[int | None] = mapped_column(Integer)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AnalyticsWatermark(Base):
    """When a workspace's analytics were last refreshed (investigations changed since are
    refreshed next)."""

    __tablename__ = "analytics_watermarks"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
