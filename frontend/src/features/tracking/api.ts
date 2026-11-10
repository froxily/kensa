import { ApiError, getJson, isRecord, postJson } from "../../lib/api/client";
export interface Repository {
  id: string;
  owner: string;
  repo: string;
  html_url: string;
  default_branch: string;
  history_days: number;
  added_at: string;
  last_sync_at: string | null;
  complete_through: string | null;
  runs: number;
  failed_runs: number;
  syncing: boolean;
  last_batch: { status: string; message: string | null } | null;
}
const nullableString = (v: unknown) => v === null || typeof v === "string";
function isRepository(v: unknown): v is Repository {
  return (
    isRecord(v) &&
    ["id", "owner", "repo", "html_url", "default_branch", "added_at"].every(
      (k) => typeof v[k] === "string",
    ) &&
    ["history_days", "runs", "failed_runs"].every((k) => typeof v[k] === "number") &&
    nullableString(v.last_sync_at) &&
    nullableString(v.complete_through) &&
    typeof v.syncing === "boolean" &&
    (v.last_batch === null ||
      (isRecord(v.last_batch) &&
        typeof v.last_batch.status === "string" &&
        nullableString(v.last_batch.message)))
  );
}
export async function listRepositories(): Promise<Repository[]> {
  const data = await getJson("/api/history/repositories");
  if (!Array.isArray(data) || !data.every(isRepository))
    throw new ApiError("Unexpected response", null);
  return data;
}
export async function trackRepository(url: string): Promise<Repository> {
  const data = await postJson("/api/history/repositories", { url });
  if (!isRepository(data)) throw new ApiError("Unexpected response", null);
  return data;
}
export async function syncRepository(id: string): Promise<void> {
  const data = await postJson(`/api/history/repositories/${encodeURIComponent(id)}/sync`, {});
  if (!isRecord(data) || typeof data.job_id !== "string" || typeof data.created !== "boolean")
    throw new ApiError("Unexpected response", null);
}
export async function forgetRepository(
  id: string,
  confirm: string,
): Promise<Record<string, number>> {
  const data = await postJson(`/api/history/repositories/${encodeURIComponent(id)}/forget`, {
    confirm,
  });
  if (
    !isRecord(data) ||
    !isRecord(data.counts) ||
    !Object.values(data.counts).every((v) => typeof v === "number")
  )
    throw new ApiError("Unexpected response", null);
  return data.counts as Record<string, number>;
}
