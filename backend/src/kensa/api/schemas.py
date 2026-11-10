"""API request and response models (the HTTP contract)."""

import uuid
from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kensa.ingestion.normalize import MAX_LOG_BYTES

Provider = Literal["ollama", "mock"]


class GitHubTarget(BaseModel):
    """A failed job of a public GitHub Actions run, as returned by ``/api/github/lookup``."""

    model_config = ConfigDict(extra="forbid")

    owner: str = Field(pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
    repo: str = Field(pattern=r"^[A-Za-z0-9._-]{1,100}$")
    run_id: int = Field(ge=1, le=10**19)
    attempt: int | None = Field(default=None, ge=1, le=1000)
    job_id: int | None = Field(default=None, ge=1, le=10**19)


class CreateInvestigation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    source: Literal["paste", "upload", "sample", "github"] = "paste"
    provider: Provider | None = None
    document_name: str = Field(default="pasted.log", min_length=1, max_length=255)
    # For source "github", an optional pasted log replaces the download (D-031).
    log_text: str | None = Field(default=None, max_length=MAX_LOG_BYTES)
    sample_id: str | None = Field(default=None, pattern=r"^[a-z0-9-]{1,64}$")
    github: GitHubTarget | None = None

    @model_validator(mode="after")
    def _one_input(self) -> Self:
        if self.github is not None or self.source == "github":
            if self.github is None or self.sample_id is not None:
                raise ValueError("source 'github' requires github and no sample_id")
            self.source = "github"
            return self
        if (self.log_text is None) == (self.sample_id is None):
            raise ValueError("provide exactly one of log_text or sample_id")
        if self.sample_id is not None:
            self.source = "sample"
        elif self.source == "sample":
            raise ValueError("source 'sample' requires sample_id")
        return self


class SampleOut(BaseModel):
    id: str
    title: str
    description: str
    synthetic: bool = True


class InvestigationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    source: str
    status: str
    provider: str
    model: str | None
    rule_category: str | None
    category: str | None = None
    verification_status: str | None = None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class InvestigationPage(BaseModel):
    items: list[InvestigationSummary]
    total: int


class DocumentMeta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    line_count: int
    byte_size: int
    redaction_count: int


class DocumentContent(DocumentMeta):
    lines: list[str]


class CitationOut(BaseModel):
    ordinal: int
    evidence_label: str
    line_number: int
    quote: str
    valid: bool
    rejection_reason: str | None


class DiagnosisOut(BaseModel):
    category: str
    rule_category: str | None
    summary: str
    root_cause: str
    confidence: float
    uncertainty: str
    recommended_fixes: list[str]
    verification_status: str
    verification_notes: list[str]
    provider: str
    model: str | None
    prompt_tokens: int | None
    output_tokens: int | None
    duration_ms: int | None
    evidence_complete: bool | None
    diagnosis_attempts: int
    citations: list[CitationOut]


class EvidenceOut(BaseModel):
    label: str
    rank: int
    score: float
    channels: list[str]
    document_id: uuid.UUID
    document_name: str
    source_type: str  # log | workflow_yaml | code | doc | kb | incident
    # Repository files imported from GitHub: the commit they were read at, and a link there.
    commit_sha: str | None = None
    source_url: str | None = None
    kind: str
    step_name: str | None
    start_line: int
    end_line: int
    lines: list[str]


class SignatureOut(BaseModel):
    line_number: int
    kind: str
    value: str
    category_hint: str | None
    weight: int
    excerpt: str


class ProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ordinal: int
    title: str
    action: str
    rationale: str
    origin: str  # model | template
    target_path: str | None
    diff: str | None
    risks: list[str]
    validation_steps: list[str]
    flags: list[str]
    status: str  # proposed | approved | rejected | withdrawn
    decided_at: datetime | None
    # Withdrawn after the fact as unsafe or non-actionable (M5); kept for the audit trail.
    withdrawn_reason: str | None = None
    withdrawn_at: datetime | None = None


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    decision: str  # approved | rejected
    note: str | None
    created_at: datetime


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=1000)


class DecisionResult(BaseModel):
    decision: DecisionOut
    # False when the same decision had already been recorded (an idempotent repeat).
    created: bool
    status: str


class WorkflowRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    owner: str
    repo: str
    run_id: int
    run_number: int
    run_attempt: int
    workflow_name: str
    workflow_path: str
    event: str
    head_branch: str | None
    head_sha: str
    conclusion: str | None
    html_url: str
    job_id: int
    job_name: str
    job_html_url: str
    failed_steps: list[str]
    log_source: str  # github | pasted
    log_dropped_lines: int
    files_fetched: list[str]
    files_missing: list[str]


class InvestigationDetail(InvestigationSummary):
    documents: list[DocumentMeta]
    diagnosis: DiagnosisOut | None
    evidence: list[EvidenceOut]
    signatures: list[SignatureOut]
    proposals: list[ProposalOut]
    decision: DecisionOut | None
    github_run: WorkflowRunOut | None = None


class GitHubLookupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=500)


class GitHubStepOut(BaseModel):
    number: int
    name: str
    conclusion: str | None


class GitHubJobOut(BaseModel):
    id: int
    name: str
    conclusion: str | None
    html_url: str
    failed_steps: list[GitHubStepOut]


class GitHubRunOut(BaseModel):
    id: int
    name: str
    display_title: str
    run_number: int
    run_attempt: int
    event: str
    conclusion: str | None
    head_branch: str | None
    head_sha: str
    workflow_path: str
    html_url: str
    created_at: str


class GitHubLookupOut(BaseModel):
    kind: Literal["repository", "run"]
    owner: str
    repo: str
    html_url: str
    # kind "repository": recent failed runs. kind "run": the run and its failed jobs.
    runs: list[GitHubRunOut] = []
    run: GitHubRunOut | None = None
    attempt: int | None = None
    jobs: list[GitHubJobOut] = []
    selected_job_id: int | None = None
    # Without a token GitHub serves no job logs, so the UI asks for a pasted log instead.
    token_configured: bool


class AgentEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    attempt: int
    node: str
    event_type: str
    summary: str
    detail: dict[str, Any]
    duration_ms: int | None
    created_at: datetime


# ---------------------------------------------------------------------- v1.1: CI history ---


class TrackRepositoryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=500)
    history_days: int | None = Field(default=None, ge=1, le=400)


class EtlBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    started_at: datetime
    finished_at: datetime | None
    requests_used: int
    counts: dict[str, int]
    watermark_after: str | None
    error_code: str | None
    message: str | None


class TrackedRepositoryOut(BaseModel):
    id: uuid.UUID
    owner: str
    repo: str
    html_url: str
    default_branch: str | None
    history_days: int
    added_at: datetime
    last_sync_at: datetime | None
    # The end of the last complete sync window: runs created before it are all stored.
    complete_through: str | None
    runs: int
    failed_runs: int
    syncing: bool
    last_batch: EtlBatchOut | None


class SyncOut(BaseModel):
    job_id: uuid.UUID
    created: bool


class ForgetIn(BaseModel):
    """Forget repository deletes everything Kensa holds about it; the request must repeat the
    repository's full name, so it cannot happen by accident."""

    model_config = ConfigDict(extra="forbid")

    confirm: str = Field(min_length=3, max_length=201)


class RetentionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    older_than_days: int = Field(ge=1, le=3650)
    confirm: Literal[True]


class PurgeOut(BaseModel):
    counts: dict[str, int]


class DqFindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    check: str
    severity: str
    entity_key: str
    detail: str
    first_seen: datetime
    last_seen: datetime
    resolved_at: datetime | None
    tracked_repository_id: uuid.UUID | None
    investigation_id: uuid.UUID | None


# ------------------------------------------------- v1.1: similar failures (D-051, D-053) ---


class FingerprintOut(BaseModel):
    hash: str
    role: str
    category: str
    rule_id: str
    subject: str
    template: str
    # exact: may claim a recurrence; approximate: similarity only (D-057).
    kind: Literal["exact", "approximate"]
    # How many investigations share it; None while history matching is off.
    occurrences: int | None


class SimilarFailureOut(BaseModel):
    investigation_id: uuid.UUID
    title: str
    created_at: datetime
    match: Literal["same_failure", "related", "similar_text"]
    score: float
    earlier: bool
    category: str
    diagnosis_category: str | None
    verification_status: str | None
    # What the earlier conclusion rests on; history is never evidence for this investigation.
    provenance: Literal["human_confirmed", "verifier_corroborated", "model_hypothesis", "none"]
    resolution: str | None


class ResolutionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=3, max_length=1000)


class ResolutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provenance: str
    summary: str
    created_at: datetime


class InvestigationHistoryOut(BaseModel):
    # False: experimental history matching is off, and nothing is matched or counted.
    matching: bool
    fingerprints: list[FingerprintOut]
    similar: list[SimilarFailureOut]
    resolution: ResolutionOut | None


# ----------------------------------------------- v1.1: change-aware investigation (D-054) ---


class ChangeFactorOut(BaseModel):
    name: str
    state: Literal["same", "different", "unknown", "changed_in_range"]
    detail: str


class ChangeSuspectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rank: int
    path: str
    change_kind: str
    score: float
    # Never "cause": a change is correlated with the failure, or weakly so.
    status: Literal["correlated", "weak"]
    signals: dict[str, float]
    document_id: uuid.UUID | None


class ChangesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    comparability: str
    reasons: list[str]
    factors: list[ChangeFactorOut]
    unverified: list[str]
    baseline_run_id: int | None
    baseline_sha: str | None
    failed_sha: str
    compare_status: str | None
    commits: int
    files: int
    truncated: bool
    suspects: list[ChangeSuspectOut]
