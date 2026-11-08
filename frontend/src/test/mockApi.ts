import { vi } from "vitest";

import type { HealthResponse } from "../features/health/api";
import type {
  GitHubLookup,
  GitHubRunRecord,
  InvestigationDetail,
  InvestigationSummary,
  RemediationProposal,
} from "../features/investigations/types";

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

type Handler = (init: RequestInit | undefined, url: URL) => Response;
type Route = Handler | { body: unknown; status?: number };

function toUrl(input: RequestInfo | URL): URL {
  const href = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return new URL(href, "http://localhost");
}

/** Stubs `fetch` with routes keyed by "METHOD /path"; unknown routes return 404. */
export function mockApi(routes: Record<string, Route>) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = toUrl(input);
    const route = routes[`${init?.method ?? "GET"} ${url.pathname}`];
    if (route === undefined) {
      return Promise.resolve(jsonResponse({ detail: `not mocked: ${url.pathname}` }, 404));
    }
    if (typeof route === "function") return Promise.resolve(route(init, url));
    return Promise.resolve(jsonResponse(route.body, route.status ?? 200));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export const MODEL = "qwen3:4b-instruct-2507-q4_K_M";

export function health(overrides: Partial<HealthResponse> = {}): HealthResponse {
  return {
    status: "ok",
    version: "0.1.0",
    inference_provider: "ollama",
    database: { status: "ok", pgvector_version: "0.8.7", detail: null },
    ollama: { status: "ok", model: MODEL, detail: null },
    ...overrides,
  };
}

export const ID = "11111111-1111-4111-8111-111111111111";
export const DOC_ID = "22222222-2222-4222-8222-222222222222";

export function summary(overrides: Partial<InvestigationSummary> = {}): InvestigationSummary {
  return {
    id: ID,
    title: "Error: Missing required environment variable: VITE_API_BASE_URL",
    source: "sample",
    status: "completed",
    provider: "ollama",
    model: MODEL,
    rule_category: "missing_env_var",
    category: "missing_env_var",
    verification_status: "corroborated",
    error_code: null,
    error_message: null,
    created_at: "2026-10-30T04:00:00Z",
    started_at: "2026-10-30T04:00:01Z",
    finished_at: "2026-10-30T04:00:05Z",
    ...overrides,
  };
}

export function detail(overrides: Partial<InvestigationDetail> = {}): InvestigationDetail {
  return {
    ...summary(),
    documents: [
      { id: DOC_ID, name: "build.log", line_count: 30, byte_size: 2000, redaction_count: 1 },
    ],
    diagnosis: {
      category: "missing_env_var",
      rule_category: "missing_env_var",
      summary: "The build needs VITE_API_BASE_URL, which is not set.",
      root_cause: "check-env.mjs throws because VITE_API_BASE_URL is undefined in the job.",
      confidence: 0.9,
      uncertainty: "Which secret was meant to supply it.",
      recommended_fixes: ["Add VITE_API_BASE_URL to the job env.", "git push --force"],
      // A rejected citation below: never "corroborated" (the backend refuses that combination).
      verification_status: "plausible",
      verification_notes: ["Fix 2 flagged for review: force-pushes or rewrites history."],
      provider: "ollama",
      model: MODEL,
      prompt_tokens: 900,
      output_tokens: 150,
      duration_ms: 2100,
      evidence_complete: true,
      diagnosis_attempts: 1,
      citations: [
        {
          ordinal: 0,
          evidence_label: "E1",
          line_number: 24,
          quote: "Missing required environment variable: VITE_API_BASE_URL",
          valid: true,
          rejection_reason: null,
        },
        {
          ordinal: 1,
          evidence_label: "E1",
          line_number: 25,
          quote: "made-up text",
          valid: false,
          rejection_reason: "quote_not_found",
        },
        {
          ordinal: 2,
          evidence_label: "E2",
          line_number: 9,
          quote: "Add the variable to the job env",
          valid: true,
          rejection_reason: null,
        },
      ],
    },
    evidence: [
      {
        label: "E1",
        rank: 1,
        score: 0.03,
        channels: ["signature", "fts"],
        document_id: DOC_ID,
        document_name: "build.log",
        source_type: "log",
        commit_sha: null,
        source_url: null,
        kind: "error_window",
        step_name: "Run npm run build",
        start_line: 18,
        end_line: 27,
        lines: Array.from({ length: 10 }, (_, i) => `evidence line ${String(18 + i)}`),
      },
      {
        label: "E2",
        rank: 2,
        score: 0.02,
        channels: ["vector"],
        document_id: "33333333-3333-4333-8333-333333333333",
        document_name: "kb/ci-troubleshooting/missing-environment-variables.md",
        source_type: "kb",
        commit_sha: null,
        source_url: null,
        kind: "markdown_section",
        step_name: null,
        start_line: 8,
        end_line: 10,
        lines: ["## Fixes", "- Add the variable to the job env.", ""],
      },
    ],
    signatures: [
      {
        line_number: 24,
        kind: "missing_env",
        value: "VITE_API_BASE_URL",
        category_hint: "missing_env_var",
        weight: 3,
        excerpt: "Error: Missing required environment variable: VITE_API_BASE_URL",
      },
    ],
    proposals: [],
    decision: null,
    github_run: null,
    ...overrides,
  };
}

export function proposals(): RemediationProposal[] {
  return [
    {
      id: "p1",
      ordinal: 1,
      title: "Update workflow",
      action: "Set the job environment.",
      rationale: "The variable is missing.",
      origin: "model",
      target_path: ".github/workflows/ci.yml",
      diff: "--- a/ci.yml\n+++ b/ci.yml\n@@ -1 +1 @@\n-old\n+new",
      risks: ["Check secret scope."],
      flags: ["Review environment."],
      validation_steps: ["Review the workflow.", "Re-run the job."],
      status: "proposed",
      decided_at: null,
      withdrawn_reason: null,
      withdrawn_at: null,
    },
    {
      id: "p2",
      ordinal: 2,
      title: "Check configuration",
      action: "Inspect the configuration.",
      rationale: "",
      origin: "template",
      target_path: null,
      diff: null,
      risks: [],
      flags: [],
      validation_steps: [],
      status: "proposed",
      decided_at: null,
      withdrawn_reason: null,
      withdrawn_at: null,
    },
  ];
}

export function documentLines(count = 30): string[] {
  return Array.from({ length: count }, (_, i) =>
    i === 23
      ? "Error: Missing required environment variable: VITE_API_BASE_URL"
      : `line ${String(i + 1)}`,
  );
}

type Listener = (event: MessageEvent<string>) => void;

/** Minimal EventSource stand-in (jsdom has none). */
export class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readonly url: string;
  closed = false;
  private listeners = new Map<string, Listener[]>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: Listener): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  emit(type: string, data: unknown): void {
    const event = new MessageEvent(type, { data: JSON.stringify(data) });
    for (const listener of this.listeners.get(type) ?? []) listener(event);
  }

  close(): void {
    this.closed = true;
  }
}

export function githubRunRecord(): GitHubRunRecord {
  return {
    owner: "octo",
    repo: "project",
    run_id: 123,
    run_number: 42,
    run_attempt: 2,
    workflow_name: "CI",
    workflow_path: ".github/workflows/ci.yml",
    event: "push",
    head_branch: "main",
    head_sha: "abcdef1234567890",
    conclusion: "failure",
    html_url: "https://github.com/octo/project/actions/runs/123",
    job_id: 456,
    job_name: "build",
    job_html_url: "https://github.com/octo/project/actions/runs/123/job/456",
    failed_steps: ["4. Test"],
    log_source: "github",
    log_dropped_lines: 0,
    files_fetched: [".github/workflows/ci.yml"],
    files_missing: [],
  };
}

export function githubLookupRun(tokenConfigured: boolean): GitHubLookup {
  const record = githubRunRecord();
  return {
    kind: "run",
    owner: record.owner,
    repo: record.repo,
    html_url: record.html_url,
    runs: [],
    run: {
      id: record.run_id,
      name: record.workflow_name,
      display_title: "CI failed",
      run_number: record.run_number,
      run_attempt: record.run_attempt,
      event: record.event,
      conclusion: record.conclusion,
      head_branch: record.head_branch,
      head_sha: record.head_sha,
      workflow_path: record.workflow_path,
      html_url: record.html_url,
      created_at: "2026-10-30T04:00:00Z",
    },
    attempt: 2,
    jobs: [
      {
        id: record.job_id,
        name: record.job_name,
        conclusion: "failure",
        html_url: record.job_html_url,
        failed_steps: [{ number: 4, name: "Test", conclusion: "failure" }],
      },
    ],
    selected_job_id: record.job_id,
    token_configured: tokenConfigured,
  };
}

export function githubLookupRepository(): GitHubLookup {
  const lookup = githubLookupRun(true);
  return {
    ...lookup,
    kind: "repository",
    html_url: "https://github.com/octo/project",
    runs: lookup.run ? [lookup.run] : [],
    run: null,
    attempt: null,
    jobs: [],
    selected_job_id: null,
  };
}
