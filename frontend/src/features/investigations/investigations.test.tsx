import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import {
  DOC_ID,
  FakeEventSource,
  ID,
  detail,
  documentLines,
  health,
  githubLookupRepository,
  githubLookupRun,
  githubRunRecord,
  jsonResponse,
  mockApi,
  proposals,
  summary,
} from "../../test/mockApi";
import { renderApp } from "../../test/render";
import type { AgentEvent } from "./types";

const SAMPLES = [
  {
    id: "db-connection",
    title: "Test setup errors",
    description: "pytest errors.",
    synthetic: true,
  },
];

function event(seq: number, node: string, eventType: AgentEvent["event_type"] = "completed") {
  return {
    seq,
    attempt: 1,
    node,
    event_type: eventType,
    summary: `${node} summary`,
    detail: {},
    duration_ms: 5,
    created_at: "2026-10-30T04:00:00Z",
  };
}

type FetchMock = ReturnType<typeof mockApi>;

function at<T>(items: T[], index: number): T {
  const item = items[index];
  if (item === undefined) throw new Error(`no item at index ${String(index)}`);
  return item;
}

function requestUrl(input: RequestInfo | URL): string {
  return typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
}

function postedJson(fetchMock: FetchMock): unknown {
  const call = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
  const body = call?.[1]?.body;
  if (typeof body !== "string") throw new Error("no JSON POST body");
  return JSON.parse(body);
}

function investigationRoutes(overrides: Parameters<typeof detail>[0] = {}) {
  return {
    "GET /api/health": { body: health() },
    [`GET /api/investigations/${ID}`]: { body: detail(overrides) },
    [`GET /api/investigations/${ID}/events`]: { body: [event(1, "pipeline", "started")] },
    [`GET /api/investigations/${ID}/documents/${DOC_ID}`]: {
      body: { ...detail().documents[0], lines: documentLines() },
    },
  };
}

describe("overview", () => {
  it("lists investigations with status and diagnosis", async () => {
    mockApi({
      "GET /api/health": { body: health() },
      "GET /api/investigations": {
        body: {
          items: [
            summary(),
            summary({
              id: "2",
              title: "Queued one",
              status: "queued",
              category: null,
              verification_status: null,
            }),
          ],
          total: 2,
        },
      },
    });
    renderApp("/");
    const table = await screen.findByRole("table", { name: "Recent investigations" });
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(within(at(rows, 1)).getByText("Completed")).toBeInTheDocument();
    expect(within(at(rows, 1)).getByText("Missing environment variable")).toBeInTheDocument();
    expect(within(at(rows, 1)).getByText("Cause corroborated")).toBeInTheDocument();
    expect(within(at(rows, 2)).getByText("Queued")).toBeInTheDocument();
    expect(within(table).getByRole("link", { name: /VITE_API_BASE_URL/ })).toHaveAttribute(
      "href",
      `/investigations/${ID}`,
    );
  });
});

describe("new investigation", () => {
  it("submits a pasted log with the chosen engine and opens the investigation", async () => {
    const user = userEvent.setup();
    const fetchMock = mockApi({
      ...investigationRoutes({ status: "queued", diagnosis: null }),
      "GET /api/samples": { body: SAMPLES },
      "POST /api/investigations": { body: summary({ status: "queued" }), status: 201 },
    });
    renderApp("/investigations/new");
    await user.type(screen.getByLabelText("Failed CI log"), "Error: boom");
    await user.click(screen.getByLabelText(/Rules only/));
    await user.click(screen.getByRole("button", { name: "Investigate" }));

    expect(
      await screen.findByRole("heading", { level: 1, name: /VITE_API_BASE_URL/ }),
    ).toBeInTheDocument();
    expect(postedJson(fetchMock)).toEqual({
      provider: "mock",
      source: "paste",
      log_text: "Error: boom",
    });
  });

  it("validates input before sending anything", async () => {
    const user = userEvent.setup();
    const fetchMock = mockApi({
      "GET /api/health": { body: health() },
      "GET /api/samples": { body: SAMPLES },
    });
    renderApp("/investigations/new");
    await user.click(screen.getByRole("button", { name: "Investigate" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Paste a log first.");

    await user.click(screen.getByLabelText("Upload file"));
    const big = new File(["x".repeat(2_000_001)], "big.log", { type: "text/plain" });
    await user.upload(screen.getByLabelText(/Log file/), big);
    await user.click(screen.getByRole("button", { name: "Investigate" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("larger than 2 MB");
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });

  it("sends a sample id and defaults to rules only when the model is unavailable", async () => {
    const user = userEvent.setup();
    const fetchMock = mockApi({
      ...investigationRoutes(),
      "GET /api/health": {
        body: health({
          status: "degraded",
          ollama: { status: "unavailable", model: "m", detail: null },
        }),
      },
      "GET /api/samples": { body: SAMPLES },
      "POST /api/investigations": { body: summary(), status: 201 },
    });
    renderApp("/investigations/new");
    expect(await screen.findByText(/local model is not available/)).toBeInTheDocument();
    await user.click(screen.getByLabelText("Sample incident"));
    await user.selectOptions(screen.getByLabelText("Sample"), "db-connection");
    await user.click(screen.getByRole("button", { name: "Investigate" }));
    await screen.findByRole("heading", { level: 1 });
    expect(postedJson(fetchMock)).toEqual({
      provider: "mock",
      source: "sample",
      sample_id: "db-connection",
    });
  });

  it("shows the server's validation message", async () => {
    const user = userEvent.setup();
    mockApi({
      "GET /api/health": { body: health() },
      "GET /api/samples": { body: SAMPLES },
      "POST /api/investigations": () => jsonResponse({ detail: "log is empty" }, 422),
    });
    renderApp("/investigations/new");
    await user.type(screen.getByLabelText("Failed CI log"), "x");
    await user.click(screen.getByRole("button", { name: "Investigate" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("log is empty");
  });
});

describe("investigation workspace", () => {
  it("shows the report's cause status apart from its evidence check", async () => {
    const user = userEvent.setup();
    mockApi(investigationRoutes());
    renderApp(`/investigations/${ID}`);

    const report = await screen.findByRole("region", { name: "Diagnosis" });
    expect(within(report).getByText("Plausible, not confirmed")).toBeInTheDocument();
    expect(within(report).getByText(/Treat this as a hypothesis/)).toBeInTheDocument();
    expect(
      within(report).getByText("2 of 3 citations found on their cited lines"),
    ).toBeInTheDocument();
    // The model's self-reported confidence is no longer shown (M5.1).
    expect(within(report).queryByText("90%")).not.toBeInTheDocument();
    expect(within(report).getAllByText("Missing environment variable").length).toBeGreaterThan(0);
    expect(within(report).getByText(/Rejected: quote_not_found/)).toBeInTheDocument();
    expect(within(report).getByText("Flagged for review")).toBeInTheDocument();

    await user.click(
      within(report).getByRole("button", { name: /^Show line 24 in the log:\s*L24:/ }),
    );
    const log = await screen.findByRole("region", { name: "Log lines" });
    await waitFor(() => {
      expect(log.querySelector('[data-line="24"]')).toHaveAttribute("aria-current", "location");
    });
    expect(screen.getByText("1 secret(s) redacted before storage")).toBeInTheDocument();
  });

  it("points a citation of non-log evidence at its evidence card, not the log", async () => {
    const user = userEvent.setup();
    mockApi(investigationRoutes());
    renderApp(`/investigations/${ID}`);

    const report = await screen.findByRole("region", { name: "Diagnosis" });
    const citation = within(report).getByRole("button", {
      name: /^Show evidence E2:\s*kb\/ci-troubleshooting\/missing-environment-variables\.md L9:/,
    });
    const card = screen.getByText("Knowledge base").closest("li");
    expect(card).toHaveAttribute("id", "evidence-E2");
    expect(
      within(card as HTMLElement).queryByRole("button", { name: /L8–10/ }),
    ).not.toBeInTheDocument();

    await user.click(citation);
    expect(card).toHaveFocus();
    // The knowledge-note line number must not mark (and so reveal) log line 9.
    const log = await screen.findByRole("region", { name: "Log lines" });
    expect(log.querySelector('[data-line="9"]')).toBeNull();
  });

  it("does not present a cause when none could be established", async () => {
    const base = detail();
    mockApi(
      investigationRoutes({
        diagnosis: base.diagnosis && {
          ...base.diagnosis,
          verification_status: "not_established",
          category: "unknown",
        },
      }),
    );
    renderApp(`/investigations/${ID}`);
    expect(await screen.findByText("Cause not established")).toBeInTheDocument();
    expect(screen.queryByText(base.diagnosis?.summary ?? "")).not.toBeInTheDocument();
  });

  it("explains an abstention when the log does not show the failure", async () => {
    const base = detail();
    mockApi(
      investigationRoutes({
        diagnosis: base.diagnosis && {
          ...base.diagnosis,
          verification_status: "not_established",
          category: "unknown",
          evidence_complete: false,
          diagnosis_attempts: 0,
          citations: [],
        },
      }),
    );
    renderApp(`/investigations/${ID}`);
    expect(await screen.findByText("Cause not established")).toBeInTheDocument();
    expect(screen.getByText(/did not ask the model to guess/)).toBeInTheDocument();
  });

  it("offers a retry when the investigation failed", async () => {
    const user = userEvent.setup();
    const fetchMock = mockApi({
      ...investigationRoutes({
        status: "failed",
        diagnosis: null,
        error_code: "model_unavailable",
        error_message: "The local model server (Ollama) is not reachable.",
      }),
      [`POST /api/investigations/${ID}/retry`]: { body: summary({ status: "queued" }) },
    });
    renderApp(`/investigations/${ID}`);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Ollama) is not reachable");
    await user.click(within(alert).getByRole("button", { name: "Retry investigation" }));
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) => init?.method === "POST" && requestUrl(input).endsWith("/retry"),
        ),
      ).toBe(true);
    });
  });

  it("follows live progress over server-sent events", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    mockApi(investigationRoutes({ status: "running", diagnosis: null }));
    renderApp(`/investigations/${ID}`);
    expect(await screen.findByText("pipeline summary")).toBeInTheDocument();
    await waitFor(() => {
      expect(FakeEventSource.instances).toHaveLength(1);
    });
    const source = FakeEventSource.instances[0];
    expect(source?.url).toBe(`/api/investigations/${ID}/stream?after=1`);
    act(() => {
      source?.emit("agent_event", event(2, "retrieve"));
    });
    expect(await screen.findByText("retrieve summary")).toBeInTheDocument();
    act(() => {
      source?.emit("end", {});
    });
    expect(source?.closed).toBe(true);
  });

  it("explains a missing investigation", async () => {
    mockApi({ "GET /api/health": { body: health() } });
    renderApp(`/investigations/${ID}`);
    expect(await screen.findByText("This investigation does not exist.")).toBeInTheDocument();
  });
});

describe("remediation review", () => {
  it("shows proposals and records an approval with a note", async () => {
    const user = userEvent.setup();
    const note = "Looks good";
    const fetchMock = mockApi({
      ...investigationRoutes({ status: "awaiting_approval", proposals: proposals() }),
      [`POST /api/investigations/${ID}/decision`]: {
        body: {
          decision: { decision: "approved", note, created_at: "2026-10-30T04:00:00Z" },
          created: true,
          status: "queued",
        },
      },
    });
    renderApp(`/investigations/${ID}`);
    const review = await screen.findByRole("region", { name: "Remediation review" });
    expect(within(review).getByText("Update workflow")).toBeInTheDocument();
    expect(within(review).getByText("Check configuration")).toBeInTheDocument();
    expect(within(review).getByText("Added:")).toBeInTheDocument();
    expect(within(review).getByText("Removed:")).toBeInTheDocument();
    expect(within(review).getByText("Check secret scope.")).toBeInTheDocument();
    expect(within(review).getByText("Review the workflow.")).toBeInTheDocument();
    expect(within(review).getByText("Re-run the job.")).toBeInTheDocument();
    await user.type(within(review).getByLabelText("Note (optional)"), note);
    await user.click(within(review).getByRole("button", { name: "Approve proposals" }));
    await waitFor(() => {
      expect(postedJson(fetchMock)).toEqual({ decision: "approved", note });
    });
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          init?.method === "POST" &&
          requestUrl(input).endsWith(`/api/investigations/${ID}/decision`),
      ),
    ).toBe(true);
  });

  it("keeps the diagnosis readable after rejection", async () => {
    mockApi(
      investigationRoutes({
        proposals: proposals().map((p) => ({ ...p, status: "rejected" })),
        decision: { decision: "rejected", note: null, created_at: "2026-10-30T04:00:00Z" },
      }),
    );
    renderApp(`/investigations/${ID}`);
    const review = await screen.findByRole("region", { name: "Remediation review" });
    expect(within(review).getByText(/^Rejected on /)).toBeInTheDocument();
    expect(within(review).queryByRole("button", { name: /proposals/ })).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Diagnosis" })).toBeInTheDocument();
  });

  it("shows a conflicting decision error", async () => {
    const user = userEvent.setup();
    mockApi({
      ...investigationRoutes({ status: "awaiting_approval", proposals: proposals() }),
      [`POST /api/investigations/${ID}/decision`]: {
        status: 409,
        body: { detail: "A different decision (rejected) was already recorded." },
      },
    });
    renderApp(`/investigations/${ID}`);
    await user.click(await screen.findByRole("button", { name: "Approve proposals" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "A different decision (rejected) was already recorded.",
    );
  });

  it("marks a withdrawn proposal as not actionable and keeps its content", async () => {
    const list = proposals();
    mockApi(
      investigationRoutes({
        proposals: [
          {
            ...at(list, 0),
            status: "withdrawn",
            withdrawn_reason: "unsafe under the edit checks (removes_existing_keys)",
            withdrawn_at: "2026-10-30T14:00:00Z",
          },
          at(list, 1),
        ],
      }),
    );
    renderApp(`/investigations/${ID}`);
    const review = await screen.findByRole("region", { name: "Remediation review" });
    expect(within(review).getByText("Withdrawn")).toBeInTheDocument();
    expect(within(review).getByText("Withdrawn: not actionable")).toBeInTheDocument();
    expect(within(review).getByText(/removes_existing_keys/)).toBeInTheDocument();
    expect(within(review).getByText("Added:")).toBeInTheDocument();
  });

  it("shows a repeated title, action or rationale only once", async () => {
    const repeated = "Verify the HalfUp function logic in round.go.";
    const first = at(proposals(), 0);
    mockApi(
      investigationRoutes({
        status: "awaiting_approval",
        proposals: [
          { ...first, title: repeated, action: repeated, rationale: `${repeated} ` },
          { ...at(proposals(), 1), action: "Say it once.", rationale: "Say it once." },
        ],
      }),
    );
    renderApp(`/investigations/${ID}`);
    const review = await screen.findByRole("region", { name: "Remediation review" });
    expect(within(review).getAllByText(repeated)).toHaveLength(1);
    expect(within(review).getAllByText("Say it once.")).toHaveLength(1);
  });

  it("omits the review when there are no proposals or decision", async () => {
    mockApi(investigationRoutes());
    renderApp(`/investigations/${ID}`);
    await screen.findByRole("region", { name: "Diagnosis" });
    expect(screen.queryByRole("region", { name: "Remediation review" })).not.toBeInTheDocument();
  });
});

describe("github import", () => {
  it.each([true, false])("looks up and imports a run (token configured: %s)", async (token) => {
    const user = userEvent.setup();
    const run = githubLookupRun(token);
    const fetchMock = mockApi({
      ...investigationRoutes(),
      "GET /api/samples": { body: SAMPLES },
      "POST /api/github/lookup": (init) =>
        jsonResponse(
          (typeof init?.body === "string" ? (JSON.parse(init.body) as { url: string }).url : "") ===
            run.html_url
            ? run
            : githubLookupRepository(),
        ),
      "POST /api/investigations": { body: summary(), status: 201 },
    });
    renderApp("/investigations/new");
    await user.click(screen.getByLabelText("GitHub run"));
    await user.type(
      screen.getByLabelText("GitHub repository, run or job URL"),
      "https://github.com/octo/project",
    );
    await user.click(screen.getByRole("button", { name: "Look up" }));
    await user.click(await screen.findByRole("radio", { name: /CI failed/ }));
    expect(await screen.findByText("Failed step: Test")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          requestUrl(input).endsWith("/api/github/lookup") &&
          (typeof init?.body === "string" ? (JSON.parse(init.body) as { url: string }).url : "") ===
            run.html_url,
      ),
    ).toBe(true);
    if (!token) {
      await user.click(screen.getByRole("button", { name: "Investigate" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("Paste the failed job log first.");
      expect(
        fetchMock.mock.calls.some(([input]) => requestUrl(input).endsWith("/api/investigations")),
      ).toBe(false);
      await user.type(screen.getByLabelText("Failed job log"), "failure log");
    }
    await user.click(screen.getByRole("button", { name: "Investigate" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([input, init]) =>
          init?.method === "POST" && requestUrl(input).endsWith("/api/investigations"),
      );
      const body = call?.[1]?.body;
      expect(typeof body === "string" ? JSON.parse(body) : null).toEqual({
        source: "github",
        provider: "ollama",
        github: { owner: "octo", repo: "project", run_id: 123, job_id: 456, attempt: 2 },
        ...(!token ? { log_text: "failure log" } : {}),
      });
    });
  });

  it("shows lookup errors", async () => {
    const user = userEvent.setup();
    mockApi({
      "GET /api/health": { body: health() },
      "GET /api/samples": { body: SAMPLES },
      "POST /api/github/lookup": { status: 429, body: { detail: "Try again later" } },
    });
    renderApp("/investigations/new");
    await user.click(screen.getByLabelText("GitHub run"));
    await user.type(
      screen.getByLabelText("GitHub repository, run or job URL"),
      "https://github.com/octo/project",
    );
    await user.click(screen.getByRole("button", { name: "Look up" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Try again later");
  });

  it("shows run and evidence links", async () => {
    const evidence = detail().evidence.map((item, index) =>
      index === 1
        ? {
            ...item,
            commit_sha: "abcdef1234567890",
            source_url: "https://github.com/octo/project/blob/abcdef/file",
          }
        : item,
    );
    mockApi(investigationRoutes({ github_run: githubRunRecord(), evidence }));
    renderApp(`/investigations/${ID}`);
    const card = await screen.findByRole("region", { name: "GitHub run" });
    expect(within(card).getByRole("link", { name: /abcdef1/ })).toHaveAttribute(
      "href",
      "https://github.com/octo/project/commit/abcdef1234567890",
    );
    expect(within(card).getByRole("link", { name: /build/ })).toHaveAttribute(
      "href",
      githubRunRecord().job_html_url,
    );
    expect(screen.getByText("at commit abcdef1")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /View on GitHub/ })).toHaveAttribute(
      "href",
      evidence[1]?.source_url,
    );
  });
});
