import { ApiError, getJson, isRecord, postJson } from "../../lib/api/client";
import type {
  AgentEvent,
  Changes,
  History,
  Resolution,
  CreateInvestigationBody,
  DecisionBody,
  DecisionResponse,
  DocumentContent,
  GitHubLookup,
  InvestigationDetail,
  InvestigationPage,
  InvestigationSummary,
  Sample,
} from "./types";

// Light runtime checks: enough to fail loudly on a wrong endpoint or proxy page, without
// duplicating the whole backend schema.
function expect<T>(value: unknown, guard: (v: unknown) => v is T): T {
  if (!guard(value)) throw new ApiError("Unexpected response", null);
  return value;
}

function expectArray<T>(value: unknown, guard: (v: unknown) => v is T): T[] {
  if (!Array.isArray(value) || !value.every(guard)) {
    throw new ApiError("Unexpected response", null);
  }
  return value;
}

const isSummary = (v: unknown): v is InvestigationSummary =>
  isRecord(v) && typeof v.id === "string" && typeof v.status === "string";
const isDetail = (v: unknown): v is InvestigationDetail =>
  isSummary(v) && isRecord(v) && Array.isArray(v.documents) && Array.isArray(v.evidence);
const isPage = (v: unknown): v is InvestigationPage =>
  isRecord(v) && Array.isArray(v.items) && v.items.every(isSummary);
const isDocument = (v: unknown): v is DocumentContent =>
  isRecord(v) && typeof v.id === "string" && Array.isArray(v.lines);
const isEvent = (v: unknown): v is AgentEvent =>
  isRecord(v) && typeof v.seq === "number" && typeof v.node === "string";
const isSample = (v: unknown): v is Sample => isRecord(v) && typeof v.id === "string";
const isLookup = (v: unknown): v is GitHubLookup =>
  isRecord(v) && (v.kind === "repository" || v.kind === "run") && Array.isArray(v.runs);
const isDecisionResponse = (v: unknown): v is DecisionResponse =>
  isRecord(v) && isRecord(v.decision) && typeof v.created === "boolean";

export const queryKeys = {
  list: (limit: number) => ["investigations", "list", limit] as const,
  detail: (id: string) => ["investigations", "detail", id] as const,
  events: (id: string) => ["investigations", "events", id] as const,
  document: (id: string, documentId: string) =>
    ["investigations", "document", id, documentId] as const,
  samples: ["samples"] as const,
  history: (id: string) => ["investigations", "history", id] as const,
  changes: (id: string) => ["investigations", "changes", id] as const,
};

const enc = encodeURIComponent;

export async function listInvestigations(limit: number): Promise<InvestigationPage> {
  return expect(await getJson(`/api/investigations?limit=${String(limit)}`), isPage);
}

export async function getInvestigation(id: string): Promise<InvestigationDetail> {
  return expect(await getJson(`/api/investigations/${enc(id)}`), isDetail);
}

export async function getDocument(id: string, documentId: string): Promise<DocumentContent> {
  const body = await getJson(`/api/investigations/${enc(id)}/documents/${enc(documentId)}`);
  return expect(body, isDocument);
}

export async function listEvents(id: string): Promise<AgentEvent[]> {
  return expectArray(await getJson(`/api/investigations/${enc(id)}/events`), isEvent);
}

export async function listSamples(): Promise<Sample[]> {
  return expectArray(await getJson("/api/samples"), isSample);
}

export async function createInvestigation(
  body: CreateInvestigationBody,
): Promise<InvestigationSummary> {
  // A GitHub import downloads the job log and repository files first, so allow more time.
  const timeoutMs = body.source === "github" ? 120_000 : 30_000;
  const created = await postJson("/api/investigations", body, { timeoutMs });
  return expect(created, isSummary);
}

export async function retryInvestigation(id: string): Promise<InvestigationSummary> {
  return expect(await postJson(`/api/investigations/${enc(id)}/retry`, {}), isSummary);
}

/** Read-only lookup of a public GitHub repository, run or job URL (M4). */
export async function lookupGitHub(url: string): Promise<GitHubLookup> {
  return expect(await postJson("/api/github/lookup", { url }, { timeoutMs: 60_000 }), isLookup);
}

export async function decideInvestigation(
  id: string,
  body: DecisionBody,
): Promise<DecisionResponse> {
  const response = await postJson(`/api/investigations/${enc(id)}/decision`, body);
  return expect(response, isDecisionResponse);
}

export function streamUrl(id: string, after: number): string {
  return `/api/investigations/${enc(id)}/stream?after=${String(after)}`;
}

const oneOf = (value: unknown, values: readonly string[]) =>
  typeof value === "string" && values.includes(value);
const nullableString = (v: unknown) => v === null || typeof v === "string";
const isResolution = (v: unknown): v is Resolution =>
  isRecord(v) &&
  oneOf(v.provenance, ["human_confirmed", "verifier_corroborated", "model_hypothesis", "none"]) &&
  typeof v.summary === "string" &&
  typeof v.created_at === "string";
const isHistory = (v: unknown): v is History =>
  isRecord(v) &&
  typeof v.matching === "boolean" &&
  Array.isArray(v.fingerprints) &&
  v.fingerprints.every(
    (f: unknown) =>
      isRecord(f) &&
      typeof f.hash === "string" &&
      oneOf(f.role, ["primary", "secondary"]) &&
      typeof f.category === "string" &&
      typeof f.rule_id === "string" &&
      typeof f.subject === "string" &&
      typeof f.template === "string" &&
      oneOf(f.kind, ["exact", "approximate"]) &&
      (f.occurrences === null || typeof f.occurrences === "number"),
  ) &&
  Array.isArray(v.similar) &&
  v.similar.every(
    (x: unknown) =>
      isRecord(x) &&
      typeof x.investigation_id === "string" &&
      typeof x.title === "string" &&
      typeof x.created_at === "string" &&
      oneOf(x.match, ["same_failure", "related", "similar_text"]) &&
      typeof x.score === "number" &&
      typeof x.earlier === "boolean" &&
      typeof x.category === "string" &&
      nullableString(x.diagnosis_category) &&
      nullableString(x.verification_status) &&
      oneOf(x.provenance, [
        "human_confirmed",
        "verifier_corroborated",
        "model_hypothesis",
        "none",
      ]) &&
      nullableString(x.resolution),
  ) &&
  (v.resolution === null || isResolution(v.resolution));
const isChanges = (v: unknown): v is Changes =>
  isRecord(v) &&
  oneOf(v.comparability, [
    "comparable",
    "partially_comparable",
    "incomparable",
    "identical",
    "no_baseline",
    "history_unavailable",
  ]) &&
  Array.isArray(v.reasons) &&
  v.reasons.every((x: unknown) => typeof x === "string") &&
  Array.isArray(v.unverified) &&
  v.unverified.every((x: unknown) => typeof x === "string") &&
  Array.isArray(v.factors) &&
  v.factors.every(
    (x: unknown) =>
      isRecord(x) &&
      typeof x.name === "string" &&
      oneOf(x.state, ["same", "different", "unknown", "changed_in_range"]) &&
      typeof x.detail === "string",
  ) &&
  Array.isArray(v.suspects) &&
  v.suspects.every(
    (x: unknown) =>
      isRecord(x) &&
      typeof x.rank === "number" &&
      typeof x.path === "string" &&
      typeof x.change_kind === "string" &&
      typeof x.score === "number" &&
      oneOf(x.status, ["correlated", "weak"]) &&
      isRecord(x.signals) &&
      Object.values(x.signals).every((n) => typeof n === "number") &&
      nullableString(x.document_id),
  ) &&
  typeof v.truncated === "boolean" &&
  (v.baseline_run_id === null || typeof v.baseline_run_id === "number") &&
  nullableString(v.baseline_sha) &&
  typeof v.failed_sha === "string" &&
  nullableString(v.compare_status) &&
  typeof v.commits === "number" &&
  typeof v.files === "number";
export async function getHistory(id: string): Promise<History> {
  return expect(await getJson(`/api/investigations/${enc(id)}/history`), isHistory);
}
export async function getChanges(id: string): Promise<Changes | null> {
  const result = await getJson(`/api/investigations/${enc(id)}/changes`);
  return result === null ? null : expect(result, isChanges);
}
export async function saveResolution(id: string, summary: string): Promise<Resolution> {
  return expect(
    await postJson(`/api/investigations/${enc(id)}/resolution`, { summary }),
    isResolution,
  );
}
