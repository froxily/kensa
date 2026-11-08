// The only place the UI talks HTTP. Components go through feature-level query functions.

import { ApiError, isRecord } from "./errors";
import { IS_REPLAY } from "./mode";

export { ApiError, isRecord } from "./errors";

const DEFAULT_TIMEOUT_MS = 10_000;

interface RequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

/** FastAPI errors are `{detail: string}` or `{detail: [{msg: string}, …]}`. */
function errorMessage(body: unknown, status: number): string {
  if (isRecord(body)) {
    const detail = body.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0 && isRecord(detail[0])) {
      const first = detail[0].msg;
      if (typeof first === "string") return first;
    }
  }
  return `Request failed with status ${String(status)}`;
}

async function request(
  method: "GET" | "POST",
  path: string,
  body: unknown,
  options: RequestOptions,
): Promise<unknown> {
  if (IS_REPLAY) {
    // Loaded only in the replay build, which answers from recorded runs instead of HTTP.
    const { replayRequest } = await import("./replay");
    return replayRequest(method, path, body);
  }
  const controller = new AbortController();
  const timer = setTimeout(() => {
    controller.abort();
  }, options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  const forwardAbort = () => {
    controller.abort();
  };
  options.signal?.addEventListener("abort", forwardAbort);

  try {
    const headers: Record<string, string> = { Accept: "application/json" };
    const init: RequestInit = { method, headers, signal: controller.signal };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
    const response = await fetch(path, init);
    const parsed = (await response.json().catch(() => null)) as unknown;
    if (!response.ok) throw new ApiError(errorMessage(parsed, response.status), response.status);
    return parsed;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError("Network error", null);
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", forwardAbort);
  }
}

export function getJson(path: string, options: RequestOptions = {}): Promise<unknown> {
  return request("GET", path, undefined, options);
}

export function postJson(
  path: string,
  body: unknown,
  options: RequestOptions = {},
): Promise<unknown> {
  return request("POST", path, body, options);
}
