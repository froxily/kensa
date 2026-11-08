import { ApiError, getJson, isRecord } from "../../lib/api/client";

export type ComponentStatus = "ok" | "unavailable" | "model_missing" | "error" | "disabled";

export interface HealthResponse {
  status: "ok" | "degraded";
  version: string;
  inference_provider: "ollama" | "mock";
  database: {
    status: "ok" | "unavailable";
    pgvector_version: string | null;
    detail: string | null;
  };
  ollama: { status: ComponentStatus; model: string; detail: string | null };
}

export const healthQueryKey = ["health"] as const;

function isHealthResponse(value: unknown): value is HealthResponse {
  return (
    isRecord(value) &&
    (value.status === "ok" || value.status === "degraded") &&
    typeof value.version === "string" &&
    isRecord(value.database) &&
    typeof value.database.status === "string" &&
    isRecord(value.ollama) &&
    typeof value.ollama.status === "string" &&
    typeof value.ollama.model === "string"
  );
}

export async function fetchHealth({
  signal,
}: { signal?: AbortSignal } = {}): Promise<HealthResponse> {
  const body = await getJson("/api/health", signal ? { signal } : {});
  if (!isHealthResponse(body)) throw new ApiError("Unexpected health response", null);
  return body;
}
