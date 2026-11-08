import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MODEL, health, jsonResponse, mockApi } from "../../test/mockApi";
import { renderApp } from "../../test/render";

const EMPTY = { body: { items: [], total: 0 } };
// The header indicator lives in the page banner; the panel lives in the main content.
const banner = () => within(screen.getByRole("banner"));

describe("health indicator and service panel", () => {
  it("reports ready when every component is ok", async () => {
    mockApi({ "GET /api/health": { body: health() }, "GET /api/investigations": EMPTY });
    renderApp("/");
    expect(await banner().findByText("All services ready")).toBeInTheDocument();
    expect(await screen.findByText(`${MODEL} · Ready`)).toBeInTheDocument();
    expect(screen.getByText("0.8.7")).toBeInTheDocument();
  });

  it("reports degraded and explains a missing model", async () => {
    mockApi({
      "GET /api/health": {
        body: health({
          status: "degraded",
          ollama: { status: "model_missing", model: MODEL, detail: null },
        }),
      },
      "GET /api/investigations": EMPTY,
    });
    renderApp("/");
    expect(await banner().findByText("Degraded")).toBeInTheDocument();
    expect(await screen.findByText(`${MODEL} · Model not downloaded`)).toBeInTheDocument();
  });

  it("reports the backend as unreachable on network failure", async () => {
    mockApi({
      "GET /api/health": () => {
        throw new TypeError("Failed to fetch");
      },
      "GET /api/investigations": EMPTY,
    });
    renderApp("/");
    expect(await banner().findByText("Backend unreachable")).toBeInTheDocument();
    expect(screen.getByText(/uvicorn kensa\.main:app/)).toBeInTheDocument();
  });

  it("treats an unexpected response shape as an error", async () => {
    mockApi({ "GET /api/health": { body: { hello: "world" } }, "GET /api/investigations": EMPTY });
    renderApp("/");
    expect(await banner().findByText("Backend unreachable")).toBeInTheDocument();
  });

  it("treats an HTTP error as unreachable", async () => {
    mockApi({
      "GET /api/health": () => jsonResponse({ detail: "boom" }, 500),
      "GET /api/investigations": EMPTY,
    });
    renderApp("/");
    expect(await banner().findByText("Backend unreachable")).toBeInTheDocument();
  });
});
