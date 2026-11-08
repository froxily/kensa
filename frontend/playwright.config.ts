import { defineConfig, devices } from "@playwright/test";

const API = "http://127.0.0.1:8010";
const WEB = "http://127.0.0.1:5174";
const REPLAY = "http://127.0.0.1:4174";

// End-to-end tests run the real frontend against a real backend that uses the deterministic
// rules-only provider and its own database (see scripts/e2e_server.py). Requires the Compose
// database: `docker compose up -d db`. replay.spec.ts tests the static replay build, served
// with no proxy, so it cannot reach any backend.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: { baseURL: WEB, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "uv run --directory ../backend --no-sync python ../scripts/e2e_server.py",
      url: `${API}/api/health/live`,
      timeout: 90_000,
      reuseExistingServer: false,
      stdout: "pipe",
    },
    {
      command: "npm run dev -- --port 5174 --strictPort",
      url: WEB,
      env: { KENSA_API_PROXY: API },
      timeout: 60_000,
      reuseExistingServer: false,
    },
    {
      command: "npm run build:replay && npm run preview:replay",
      url: REPLAY,
      timeout: 180_000,
      reuseExistingServer: false,
    },
  ],
});
