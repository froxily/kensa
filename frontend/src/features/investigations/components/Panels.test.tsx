import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { detail, ID, jsonResponse, mockApi } from "../../../test/mockApi";
import { renderApp } from "../../../test/render";
const changes = {
  comparability: "partially_comparable",
  reasons: [],
  factors: [{ name: "runner_image", state: "unknown", detail: "Unavailable" }],
  unverified: [],
  baseline_run_id: null,
  baseline_sha: null,
  failed_sha: "abc",
  compare_status: null,
  commits: 1,
  files: 1,
  truncated: false,
  suspects: [
    {
      rank: 1,
      path: "src/app.ts",
      change_kind: "source",
      score: 3,
      status: "correlated",
      signals: { in_log: 1 },
      document_id: null,
    },
  ],
};
const history = {
  matching: true,
  fingerprints: [],
  similar: [
    {
      investigation_id: "other",
      title: "Earlier failure",
      created_at: "2026-01-01T00:00:00Z",
      match: "same_failure",
      score: 1,
      earlier: true,
      category: "unknown",
      diagnosis_category: "unknown",
      verification_status: null,
      provenance: "human_confirmed",
      resolution: "Fixed config",
    },
    {
      investigation_id: "alike",
      title: "A failure that only looks alike",
      created_at: "2026-01-02T00:00:00Z",
      match: "similar_text",
      score: 0.5,
      earlier: true,
      category: "unknown",
      diagnosis_category: "unknown",
      verification_status: null,
      provenance: "none",
      resolution: null,
    },
  ],
  resolution: null,
};
function setup(body: object = history) {
  return mockApi({
    [`GET /api/investigations/${ID}`]: { body: detail({ documents: [] }) },
    [`GET /api/investigations/${ID}/events`]: { body: [] },
    [`GET /api/investigations/${ID}/changes`]: { body: changes },
    [`GET /api/investigations/${ID}/history`]: { body },
    [`POST /api/investigations/${ID}/resolution`]: () =>
      jsonResponse(
        {
          provenance: "human_confirmed",
          summary: "Updated config",
          created_at: "2026-01-01T00:00:00Z",
        },
        201,
      ),
  });
}
describe("investigation panels", () => {
  it("shows the disclaimer, correlated suspect and unknown factor", async () => {
    setup();
    renderApp(`/investigations/${ID}`);
    expect(await screen.findByText(/Correlation, not proof/)).toBeInTheDocument();
    expect(screen.getByText("Correlated")).toBeInTheDocument();
    expect(screen.getByText("Unknown")).toBeInTheDocument();
  });
  it("never lists a similar failure as a recurrence", async () => {
    setup();
    renderApp(`/investigations/${ID}`);
    const recurrences = await screen.findByRole("list", { name: /Recurrences/ });
    const similar = screen.getByRole("list", { name: "Similar failures" });
    expect(within(recurrences).getByText("Earlier failure")).toBeInTheDocument();
    expect(within(recurrences).queryByText("A failure that only looks alike")).toBeNull();
    expect(within(similar).getByText("A failure that only looks alike")).toBeInTheDocument();
    expect(screen.getByText(/not confirmed to be the same failure/)).toBeInTheDocument();
  });
  it("shows no match and no count while history matching is off", async () => {
    setup({
      ...history,
      matching: false,
      similar: [],
      fingerprints: [
        {
          hash: "h",
          role: "primary",
          category: "missing_env_var",
          rule_id: "env.missing",
          subject: "ORCHARD_REGION",
          template: "",
          kind: "exact",
          occurrences: null,
        },
      ],
    });
    renderApp(`/investigations/${ID}`);
    expect(await screen.findByText(/experimental and turned off/)).toBeInTheDocument();
    expect(screen.getByText("Experimental")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: /Recurrences/ })).toBeNull();
    expect(screen.queryByText(/Occurrences/)).toBeNull();
    expect(screen.getByText(/ORCHARD_REGION/)).toBeInTheDocument();
  });
  it("shows provenance and saves a resolution", async () => {
    const fetchMock = setup();
    renderApp(`/investigations/${ID}`);
    expect(await screen.findByText("Confirmed by you")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/How was this failure resolved/), "Updated config");
    await userEvent.click(screen.getByRole("button", { name: "Save resolution" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        `/api/investigations/${ID}/resolution`,
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ summary: "Updated config" }),
        }),
      );
    });
    expect(await screen.findByText("Updated config")).toBeInTheDocument();
  });
});
