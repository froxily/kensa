import { describe, expect, it } from "vitest";

import { en } from "../../i18n/en";
import { ApiError } from "./errors";
import { createReplay } from "./replay";
import type { Recording } from "./replay";

function recording(): Recording {
  const investigation = (id: string, created: string, status: string, proposals: string[]) => ({
    id,
    status,
    created_at: created,
    finished_at: created,
    proposals: proposals.map((proposalStatus) => ({ status: proposalStatus, decided_at: null })),
    decision: null,
  });
  return {
    format: 1,
    manifest: {
      recorded_at: "2026-11-02T10:00:00Z",
      commit: "abc1234",
      model: "qwen3:4b-instruct-2507-q4_K_M",
      num_ctx: 8192,
      embedding_model: "qwen3-embedding:0.6b",
      gpu: "NVIDIA GeForce RTX 3050 Laptop GPU (4 GB)",
      configuration: "agent + hybrid",
    },
    investigations: [
      investigation("old", "2026-11-02T09:00:00Z", "completed", []),
      investigation("new", "2026-11-02T09:30:00Z", "awaiting_approval", ["proposed", "withdrawn"]),
    ],
    events: { new: [{ seq: 1 }] },
    documents: { "new/doc-1": { id: "doc-1", text: "log" } },
    samples: [{ id: "missing-env-var" }],
  };
}

function rejects(call: () => unknown, status: number): ApiError {
  try {
    call();
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(status);
    return error as ApiError;
  }
  throw new Error("expected the replay to refuse the request");
}

describe("replay adapter", () => {
  it("answers the UI's GET requests from the recording", () => {
    const replay = createReplay(recording());
    const page = replay("GET", "/api/investigations?limit=1", undefined) as {
      items: { id: string }[];
      total: number;
    };
    expect(page.items.map((item) => item.id)).toEqual(["new"]);
    expect(page.total).toBe(2);
    expect(replay("GET", "/api/investigations/new", undefined)).toMatchObject({ id: "new" });
    expect(replay("GET", "/api/investigations/new/events", undefined)).toEqual([{ seq: 1 }]);
    expect(replay("GET", "/api/investigations/old/events", undefined)).toEqual([]);
    expect(replay("GET", "/api/investigations/new/documents/doc-1", undefined)).toMatchObject({
      text: "log",
    });
    expect(replay("GET", "/api/samples", undefined)).toEqual([{ id: "missing-env-var" }]);
    rejects(() => replay("GET", "/api/investigations/missing", undefined), 404);
    rejects(() => replay("GET", "/api/investigations/new/documents/other", undefined), 404);
  });

  it("refuses everything that would need a backend", () => {
    const replay = createReplay(recording());
    const create = rejects(() => replay("POST", "/api/investigations", { source: "paste" }), 501);
    expect(create.message).toBe(en.replay.unsupported);
    rejects(() => replay("POST", "/api/investigations/old/retry", {}), 501);
    rejects(() => replay("POST", "/api/github/lookup", { url: "x" }), 501);
    rejects(() => replay("GET", "/api/health", undefined), 501);
  });

  it("applies a decision in memory by the backend's rules", () => {
    const replay = createReplay(recording());
    const first = replay("POST", "/api/investigations/new/decision", {
      decision: "approved",
      note: "  looks right  ",
    }) as { created: boolean; status: string; decision: { note: string } };
    expect(first).toMatchObject({ created: true, status: "completed" });
    expect(first.decision.note).toBe("looks right");

    const detail = replay("GET", "/api/investigations/new", undefined) as {
      status: string;
      proposals: { status: string; decided_at: string | null }[];
    };
    expect(detail.status).toBe("completed");
    expect(detail.proposals.map((p) => p.status)).toEqual(["approved", "withdrawn"]);
    expect(detail.proposals[0]?.decided_at).not.toBeNull();

    const repeat = replay("POST", "/api/investigations/new/decision", { decision: "approved" });
    expect(repeat).toMatchObject({ created: false });
    rejects(
      () => replay("POST", "/api/investigations/new/decision", { decision: "rejected" }),
      409,
    );
    rejects(
      () => replay("POST", "/api/investigations/old/decision", { decision: "approved" }),
      409,
    );
    rejects(() => replay("POST", "/api/investigations/new/decision", { decision: "maybe" }), 422);
  });

  it("keeps each replay's decisions to itself and leaves the recording unchanged", () => {
    const recorded = recording();
    const first = createReplay(recorded);
    first("POST", "/api/investigations/new/decision", { decision: "rejected" });
    const second = createReplay(recorded);
    expect(second("GET", "/api/investigations/new", undefined)).toMatchObject({
      status: "awaiting_approval",
      decision: null,
    });
    expect(recorded.investigations[1]?.status).toBe("awaiting_approval");
  });
});

describe("analytics replay", () => {
  it("returns the new recorded and empty paths and refuses writes", () => {
    const data = recording();
    data.analytics = { sample: true };
    data.repositories = [{ id: "repo" }];
    data.history = { new: { sample: true } };
    data.changes = { new: { sample: true } };
    const replay = createReplay(data);
    expect(replay("GET", "/api/analytics/dashboard?days=7", undefined)).toEqual({ sample: true });
    expect(replay("GET", "/api/history/repositories", undefined)).toEqual([{ id: "repo" }]);
    expect(replay("GET", "/api/investigations/new/history", undefined)).toEqual({ sample: true });
    expect(replay("GET", "/api/investigations/new/changes", undefined)).toEqual({ sample: true });
    expect(replay("GET", "/api/investigations/old/history", undefined)).toEqual({
      matching: false,
      fingerprints: [],
      similar: [],
      resolution: null,
    });
    expect(replay("GET", "/api/investigations/old/changes", undefined)).toBeNull();
    expect(createReplay(recording())("GET", "/api/analytics/dashboard", undefined)).toMatchObject({
      summary: { runs: 0 },
    });
    for (const path of [
      "/api/history/repositories",
      "/api/analytics/dashboard",
      "/api/investigations/new/resolution",
    ])
      rejects(() => replay("POST", path, {}), 501);
  });
});
