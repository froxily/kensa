import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi, jsonResponse, health } from "../test/mockApi";
import { renderApp } from "../test/render";

const dashboard = {
  history_matching: true,
  filters: { days: 30, start: "", end: "", repository: null, workflow: null, origins: [] },
  summary: {
    runs: 42,
    failed_runs: 4,
    failure_rate: 0.1,
    investigations: 3,
    corroborated: 2,
    latency_p50_seconds: null,
    latency_p95_seconds: 10,
    recurring_failures: 0,
    open_quality_findings: 0,
  },
  trends: [{ day: "2026-11-01", runs: 42, failed_runs: 4, investigations: 3, corroborated: 2 }],
  categories: [],
  workflows: [],
  recurring: [],
  freshness: [],
  quality: [],
  options: { repositories: [], workflows: [] },
};
const repo = {
  id: "r1",
  owner: "octo",
  repo: "test",
  html_url: "https://github.com/octo/test",
  default_branch: "main",
  history_days: 30,
  added_at: "2026-01-01",
  last_sync_at: null,
  complete_through: null,
  runs: 1,
  failed_runs: 1,
  syncing: false,
  last_batch: null,
};
afterEach(() => vi.unstubAllGlobals());
describe("analytics", () => {
  it("renders KPIs and chart data and updates the range", async () => {
    const fetch = mockApi({
      "GET /api/health": { body: health() },
      "GET /api/analytics/dashboard": { body: dashboard },
      "GET /api/history/repositories": { body: [] },
    });
    renderApp("/analytics");
    expect((await screen.findAllByText("42")).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("table", { hidden: true }).length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText("Range"), { target: { value: "7" } });
    await waitFor(() => {
      expect(
        fetch.mock.calls.some(([url]) => typeof url === "string" && url.includes("days=7")),
      ).toBe(true);
    });
  });
  it("shows empty guidance", async () => {
    mockApi({
      "GET /api/health": { body: health() },
      "GET /api/analytics/dashboard": {
        body: { ...dashboard, summary: { ...dashboard.summary, runs: 0, investigations: 0 } },
      },
      "GET /api/history/repositories": { body: [] },
    });
    renderApp("/analytics");
    expect(await screen.findByText(/No data yet/)).toBeInTheDocument();
  });
  it("says recurring failures are off while history matching is off", async () => {
    mockApi({
      "GET /api/health": { body: health() },
      "GET /api/analytics/dashboard": {
        body: {
          ...dashboard,
          history_matching: false,
          summary: { ...dashboard.summary, recurring_failures: null },
        },
      },
      "GET /api/history/repositories": { body: [] },
    });
    renderApp("/analytics");
    expect(await screen.findByText(/experimental and turned off/)).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Recurring failures", hidden: true })).toBeNull();
  });
  it("requires the exact repository name before forgetting", async () => {
    const fetch = mockApi({
      "GET /api/health": { body: health() },
      "GET /api/analytics/dashboard": { body: dashboard },
      "GET /api/history/repositories": { body: [repo] },
      "POST /api/history/repositories/r1/forget": () => jsonResponse({ counts: { runs: 1 } }),
    });
    renderApp("/analytics");
    fireEvent.click(await screen.findByRole("button", { name: "Forget" }));
    const form = screen.getByLabelText("Type octo/test to confirm").closest("form");
    if (!form) throw new Error("missing form");
    const submit = within(form).getByRole("button", { name: "Forget" });
    expect(submit).toBeDisabled();
    fireEvent.change(within(form).getByRole("textbox"), { target: { value: "octo/Test" } });
    expect(submit).toBeDisabled();
    fireEvent.change(within(form).getByRole("textbox"), { target: { value: "octo/test" } });
    fireEvent.click(submit);
    await waitFor(() => {
      expect(
        fetch.mock.calls.some(([url]) => typeof url === "string" && url.endsWith("/forget")),
      ).toBe(true);
    });
  });
});
