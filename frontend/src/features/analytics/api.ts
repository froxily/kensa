import { ApiError, getJson, isRecord } from "../../lib/api/client";

export interface Dashboard {
  // Experimental history matching (D-057); off: no recurring failures are counted.
  history_matching: boolean;
  filters: {
    days: number;
    start: string;
    end: string;
    repository: string | null;
    workflow: string | null;
    origins: string[];
  };
  summary: {
    runs: number;
    failed_runs: number;
    failure_rate: number | null;
    investigations: number;
    corroborated: number;
    latency_p50_seconds: number | null;
    latency_p95_seconds: number | null;
    recurring_failures: number | null;
    open_quality_findings: number;
  };
  trends: {
    day: string;
    runs: number;
    failed_runs: number;
    investigations: number;
    corroborated: number;
  }[];
  categories: { category: string; investigations: number; corroborated: number }[];
  workflows: {
    repository: string;
    workflow: string;
    runs: number;
    failed_runs: number;
    investigations: number;
    failure_rate: number | null;
  }[];
  recurring: {
    hash: string;
    category: string;
    subject: string;
    template: string;
    occurrences: number;
    first_seen: string;
    last_seen: string;
    investigation_ids: string[];
  }[];
  freshness: {
    id: string;
    repository: string;
    last_sync_at: string | null;
    complete_through: string | null;
    last_status: string | null;
    lag_hours: number | null;
  }[];
  quality: { check: string; severity: string; open: number }[];
  options: { repositories: string[]; workflows: string[] };
}
export interface Filters {
  days: number;
  repository: string;
  workflow: string;
  include_all_origins: boolean;
}
const strings = (v: unknown): v is string[] =>
  Array.isArray(v) && v.every((x) => typeof x === "string");
const rows = (v: unknown, fields: Record<string, string>): boolean =>
  Array.isArray(v) &&
  v.every(
    (x) =>
      isRecord(x) &&
      Object.entries(fields).every(([k, t]) =>
        t === "nullableNumber"
          ? x[k] === null || typeof x[k] === "number"
          : t === "strings"
            ? strings(x[k])
            : typeof x[k] === t,
      ),
  );
export function isDashboard(v: unknown): v is Dashboard {
  if (!isRecord(v) || !isRecord(v.summary) || !isRecord(v.filters) || !isRecord(v.options))
    return false;
  const s = v.summary;
  return (
    ["runs", "failed_runs", "investigations", "corroborated", "open_quality_findings"].every(
      (k) => typeof s[k] === "number",
    ) &&
    typeof v.history_matching === "boolean" &&
    ["failure_rate", "latency_p50_seconds", "latency_p95_seconds", "recurring_failures"].every(
      (k) => s[k] === null || typeof s[k] === "number",
    ) &&
    strings(v.options.repositories) &&
    strings(v.options.workflows) &&
    rows(v.trends, {
      day: "string",
      runs: "number",
      failed_runs: "number",
      investigations: "number",
      corroborated: "number",
    }) &&
    rows(v.categories, { category: "string", investigations: "number", corroborated: "number" }) &&
    rows(v.workflows, {
      repository: "string",
      workflow: "string",
      runs: "number",
      failed_runs: "number",
      investigations: "number",
      failure_rate: "nullableNumber",
    }) &&
    rows(v.recurring, {
      hash: "string",
      category: "string",
      subject: "string",
      template: "string",
      occurrences: "number",
      last_seen: "string",
      investigation_ids: "strings",
    }) &&
    rows(v.freshness, { id: "string", repository: "string", lag_hours: "nullableNumber" }) &&
    rows(v.quality, { check: "string", severity: "string", open: "number" })
  );
}
export async function getDashboard(filters: Filters): Promise<Dashboard> {
  const params = new URLSearchParams({
    days: String(filters.days),
    repository: filters.repository,
    workflow: filters.workflow,
    include_all_origins: String(filters.include_all_origins),
  });
  const data = await getJson(`/api/analytics/dashboard?${params.toString()}`);
  if (!isDashboard(data)) throw new ApiError("Unexpected response", null);
  return data;
}
