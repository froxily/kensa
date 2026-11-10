// Replay mode: answers the UI's API calls from runs recorded by scripts/record_replays.py, so the
// replay build works with no backend, model or network.
// - GET requests return the recorded responses.
// - A decision on remediation proposals changes an in-memory copy, for this browser tab only, by
//   the backend's rules (kensa.investigations.service.decide). The agent's resume is not
//   replayed, so the investigation goes straight to "completed" and no events are invented.
// - Everything else (new investigations, retries, GitHub lookups, health) is refused.

import { currentMessages } from "../../i18n";
import { ApiError, isRecord } from "./errors";

export interface ReplayManifest {
  recorded_at: string;
  commit: string;
  model: string;
  num_ctx: number;
  embedding_model: string;
  gpu: string;
  configuration: string;
}

interface RecordedDecision {
  decision: "approved" | "rejected";
  note: string | null;
  created_at: string;
}

interface RecordedInvestigation {
  id: string;
  status: string;
  created_at: string;
  finished_at: string | null;
  proposals: { status: string; decided_at: string | null }[];
  decision: RecordedDecision | null;
}

/** The file written by scripts/record_replays.py. The UI's own type guards check each response. */
export interface Recording {
  format: 1 | 2;
  analytics?: unknown;
  repositories?: unknown;
  history?: Record<string, unknown>;
  changes?: Record<string, unknown>;
  manifest: ReplayManifest;
  investigations: RecordedInvestigation[];
  /** Agent events by investigation id. */
  events: Record<string, unknown[]>;
  /** Document contents by "<investigation id>/<document id>". */
  documents: Record<string, unknown>;
  samples: unknown[];
}

type Method = "GET" | "POST";
type Handler = (method: Method, path: string, body: unknown) => unknown;

export function createReplay(recording: Recording): Handler {
  const investigations = new Map(
    recording.investigations.map((item) => [item.id, structuredClone(item)]),
  );

  function find(id: string): RecordedInvestigation {
    const found = investigations.get(id);
    if (!found) throw new ApiError("Investigation not found", 404);
    return found;
  }

  function decide(id: string, body: unknown) {
    const investigation = find(id);
    const decision = isRecord(body) ? body.decision : undefined;
    if (decision !== "approved" && decision !== "rejected") {
      throw new ApiError("The decision must be approved or rejected.", 422);
    }
    if (investigation.decision) {
      if (investigation.decision.decision !== decision) {
        throw new ApiError(
          `A different decision (${investigation.decision.decision}) was already recorded.`,
          409,
        );
      }
      return { decision: investigation.decision, created: false, status: investigation.status };
    }
    if (investigation.status !== "awaiting_approval") {
      throw new ApiError(
        `cannot decide: investigation is ${investigation.status}, not awaiting approval`,
        409,
      );
    }
    const pending = investigation.proposals.filter((proposal) => proposal.status === "proposed");
    if (pending.length === 0) {
      throw new ApiError("cannot decide: there are no proposals awaiting a decision", 409);
    }
    const now = new Date().toISOString();
    for (const proposal of pending) {
      proposal.status = decision;
      proposal.decided_at = now;
    }
    const note = isRecord(body) && typeof body.note === "string" ? body.note.trim() : "";
    investigation.decision = { decision, note: note.slice(0, 1000) || null, created_at: now };
    investigation.status = "completed";
    investigation.finished_at = now;
    return { decision: investigation.decision, created: true, status: investigation.status };
  }

  return (method, path, body) => {
    const url = new URL(path, "http://replay.invalid");
    const [api, resource, id, child, childId, ...rest] = url.pathname
      .split("/")
      .filter(Boolean)
      .map(decodeURIComponent);
    if (api === "api" && rest.length === 0) {
      if (method === "GET" && resource === "analytics" && id === "dashboard")
        return (
          recording.analytics ?? {
            history_matching: false,
            filters: {
              days: 30,
              start: "",
              end: "",
              repository: null,
              workflow: null,
              origins: [],
            },
            summary: {
              runs: 0,
              failed_runs: 0,
              failure_rate: null,
              investigations: 0,
              corroborated: 0,
              latency_p50_seconds: null,
              latency_p95_seconds: null,
              recurring_failures: null,
              open_quality_findings: 0,
            },
            trends: [],
            categories: [],
            workflows: [],
            recurring: [],
            freshness: [],
            quality: [],
            options: { repositories: [], workflows: [] },
          }
        );
      if (
        method === "GET" &&
        resource === "history" &&
        id === "repositories" &&
        child === undefined
      )
        return recording.repositories ?? [];
      if (
        method === "GET" &&
        resource === "investigations" &&
        id &&
        child === "history" &&
        childId === undefined
      )
        return (
          recording.history?.[id] ?? {
            matching: false,
            fingerprints: [],
            similar: [],
            resolution: null,
          }
        );
      if (
        method === "GET" &&
        resource === "investigations" &&
        id &&
        child === "changes" &&
        childId === undefined
      )
        return recording.changes?.[id] ?? null;
      if (method === "GET" && resource === "samples" && id === undefined) return recording.samples;
      if (resource === "investigations" && method === "GET") {
        if (id === undefined) {
          const items = [...investigations.values()].sort((a, b) =>
            b.created_at.localeCompare(a.created_at),
          );
          const limit = Number(url.searchParams.get("limit") ?? items.length);
          return { items: items.slice(0, limit), total: items.length };
        }
        const investigation = find(id);
        if (child === undefined) return investigation;
        if (child === "events" && childId === undefined) {
          return recording.events[investigation.id] ?? [];
        }
        if (child === "documents" && childId !== undefined) {
          const document = recording.documents[`${investigation.id}/${childId}`];
          if (document === undefined) throw new ApiError("Document not found", 404);
          return document;
        }
      }
      if (resource === "investigations" && method === "POST" && id && child === "decision") {
        return decide(id, body);
      }
    }
    throw new ApiError(currentMessages().replay.unsupported, 501);
  };
}

async function fetchRecording(): Promise<Recording> {
  // The recording ships next to index.html, in the replay build only.
  const data: unknown = await fetch(`${import.meta.env.BASE_URL}recording.json`)
    .then((response) => (response.ok ? (response.json() as Promise<unknown>) : null))
    .catch(() => null);
  if (!isRecord(data) || (data.format !== 1 && data.format !== 2)) {
    throw new ApiError(currentMessages().common.unexpectedError, null);
  }
  return data as unknown as Recording;
}

let recording: Promise<Recording> | undefined;
let handler: Handler | undefined;

export function loadRecording(): Promise<Recording> {
  recording ??= fetchRecording().catch((error: unknown) => {
    recording = undefined; // the next request tries again
    throw error;
  });
  return recording;
}

export async function replayManifest(): Promise<ReplayManifest> {
  return (await loadRecording()).manifest;
}

export async function replayRequest(method: Method, path: string, body: unknown) {
  const loaded = await loadRecording();
  // One handler per tab, created once even when the first requests arrive together.
  handler ??= createReplay(loaded);
  return handler(method, path, body);
}
