import { defineConfig, devices } from "@playwright/test";

// The replay tests alone (npm run e2e:replay): only the static replay build is served, so they
// run with no backend, database or model. playwright.config.ts runs the same tests in CI.
export default defineConfig({
  testDir: "./e2e",
  testMatch: "replay.spec.ts",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: { trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  // With KENSA_REPLAY_URL the tests check a deployed copy, so no local server is started.
  ...(process.env.KENSA_REPLAY_URL
    ? {}
    : {
        webServer: {
          command: "npm run build:replay && npm run preview:replay",
          url: "http://127.0.0.1:4174",
          timeout: 180_000,
          reuseExistingServer: false,
        },
      }),
});
