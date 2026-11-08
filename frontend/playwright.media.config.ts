import { defineConfig } from "@playwright/test";

// Captures the README screenshots and demo video from the replay build (npm run media). Not part
// of CI: run it after the UI or the recording changes. Writes only to docs/media/.

export default defineConfig({
  testDir: "./media",
  outputDir: "test-results/media",
  timeout: 180_000,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:4174", viewport: { width: 1280, height: 800 } },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
  webServer: {
    command: "npm run build:replay && npm run preview:replay",
    url: "http://127.0.0.1:4174",
    reuseExistingServer: false,
    timeout: 180_000,
  },
});
