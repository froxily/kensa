// Mirrors backend/src/kensa/api/schemas.py.

export type InvestigationStatus =
  "queued" | "running" | "awaiting_approval" | "completed" | "failed";
/** Root-cause status (M5.1). Evidence validity is shown separately, from the citations. */
export type VerificationStatus = "corroborated" | "plausible" | "conflicting" | "not_established";
export type Provider = "ollama" | "mock";
export type Source = "paste" | "upload" | "sample" | "github";

export interface InvestigationSummary {
  id: string;
  title: string;
  source: Source;
  status: InvestigationStatus;
  provider: Provider;
  model: string | null;
  rule_category: string | null;
  category: string | null;
  verification_status: VerificationStatus | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface InvestigationPage {
  items: InvestigationSummary[];
  total: number;
}

export interface DocumentMeta {
  id: string;
  name: string;
  line_count: number;
  byte_size: number;
  redaction_count: number;
}

export interface DocumentContent extends DocumentMeta {
  lines: string[];
}

export interface Citation {
  ordinal: number;
  evidence_label: string;
  line_number: number;
  quote: string;
  valid: boolean;
  rejection_reason: string | null;
}

export interface Diagnosis {
  category: string;
  rule_category: string | null;
  summary: string;
  root_cause: string;
  confidence: number;
  uncertainty: string;
  recommended_fixes: string[];
  verification_status: VerificationStatus;
  verification_notes: string[];
  provider: Provider;
  model: string | null;
  prompt_tokens: number | null;
  output_tokens: number | null;
  duration_ms: number | null;
  /** false when the log did not show the failure (Kensa abstained); null before M3. */
  evidence_complete: boolean | null;
  /** How many diagnoses the verifier loop requested (1 = accepted first time). */
  diagnosis_attempts: number;
  citations: Citation[];
}

/** "withdrawn": marked unsafe or non-actionable after the fact; kept for the audit trail. */
export type ProposalStatus = "proposed" | "approved" | "rejected" | "withdrawn";
export type Decision = "approved" | "rejected";

/** A read-only remediation proposal. Approving records a decision; nothing is applied. */
export interface RemediationProposal {
  id: string;
  ordinal: number;
  title: string;
  action: string;
  rationale: string;
  /** "model": suggested by the local model; "template": deterministic rules-only text. */
  origin: "model" | "template";
  /** Repository-relative path of the file a diff targets. */
  target_path: string | null;
  /** Unified diff computed by Kensa from a validated edit; never applied. */
  diff: string | null;
  risks: string[];
  validation_steps: string[];
  /** Safety flags, e.g. "disables verification". */
  flags: string[];
  status: ProposalStatus;
  decided_at: string | null;
  withdrawn_reason: string | null;
  withdrawn_at: string | null;
}

export interface ApprovalDecision {
  decision: Decision;
  note: string | null;
  created_at: string;
}

export interface DecisionBody {
  decision: Decision;
  note?: string;
}

export interface DecisionResponse {
  decision: ApprovalDecision;
  /** false when the same decision had already been recorded (idempotent repeat). */
  created: boolean;
  status: InvestigationStatus;
}

export interface EvidenceItem {
  label: string;
  rank: number;
  score: number;
  channels: string[];
  document_id: string;
  document_name: string;
  /** log | workflow_yaml | code | doc | kb | incident */
  source_type: string;
  /** Repository files imported from GitHub: the commit they were read at. */
  commit_sha: string | null;
  /** Link to the cited lines on GitHub at that commit (external). */
  source_url: string | null;
  kind: string;
  step_name: string | null;
  start_line: number;
  end_line: number;
  lines: string[];
}

export interface Signature {
  line_number: number;
  kind: string;
  value: string;
  category_hint: string | null;
  weight: number;
  excerpt: string;
}

export interface InvestigationDetail extends InvestigationSummary {
  documents: DocumentMeta[];
  diagnosis: Diagnosis | null;
  evidence: EvidenceItem[];
  signatures: Signature[];
  proposals: RemediationProposal[];
  decision: ApprovalDecision | null;
  github_run: GitHubRunRecord | null;
}

/** The GitHub Actions run and failed job an investigation was imported from (M4). */
export interface GitHubRunRecord {
  owner: string;
  repo: string;
  run_id: number;
  run_number: number;
  run_attempt: number;
  workflow_name: string;
  workflow_path: string;
  event: string;
  head_branch: string | null;
  head_sha: string;
  conclusion: string | null;
  html_url: string;
  job_id: number;
  job_name: string;
  job_html_url: string;
  /** e.g. "4. Run tests" */
  failed_steps: string[];
  /** "github": downloaded with the read-only token; "pasted": supplied by the user. */
  log_source: "github" | "pasted";
  /** Lines dropped from the start of an over-long log (its end is kept). */
  log_dropped_lines: number;
  files_fetched: string[];
  files_missing: string[];
}

export interface GitHubStep {
  number: number;
  name: string;
  conclusion: string | null;
}

export interface GitHubJob {
  id: number;
  name: string;
  conclusion: string | null;
  html_url: string;
  failed_steps: GitHubStep[];
}

export interface GitHubRun {
  id: number;
  name: string;
  display_title: string;
  run_number: number;
  run_attempt: number;
  event: string;
  conclusion: string | null;
  head_branch: string | null;
  head_sha: string;
  workflow_path: string;
  html_url: string;
  created_at: string;
}

/** POST /api/github/lookup: a repository URL lists recent failed runs; a run or job URL
 * returns that run and its failed jobs. */
export interface GitHubLookup {
  kind: "repository" | "run";
  owner: string;
  repo: string;
  html_url: string;
  runs: GitHubRun[];
  run: GitHubRun | null;
  attempt: number | null;
  jobs: GitHubJob[];
  selected_job_id: number | null;
  /** false: GitHub serves no job logs without a token, so the user must paste the log. */
  token_configured: boolean;
}

export interface GitHubTarget {
  owner: string;
  repo: string;
  run_id: number;
  attempt?: number;
  job_id?: number;
}

export interface AgentEvent {
  seq: number;
  attempt: number;
  node: string;
  event_type: "started" | "completed" | "failed" | "info";
  summary: string;
  detail: Record<string, unknown>;
  duration_ms: number | null;
  created_at: string;
}

export interface Sample {
  id: string;
  title: string;
  description: string;
  synthetic: boolean;
}

export interface CreateInvestigationBody {
  title?: string;
  source: Source;
  provider: Provider;
  document_name?: string;
  /** For source "github": an optional pasted log used instead of downloading it. */
  log_text?: string;
  sample_id?: string;
  github?: GitHubTarget;
}

// Settled states: nothing runs until the user acts, so polling and the live stream stop.
export const TERMINAL_STATUSES: readonly InvestigationStatus[] = [
  "awaiting_approval",
  "completed",
  "failed",
];

export function isTerminal(status: InvestigationStatus): boolean {
  return TERMINAL_STATUSES.includes(status);
}
