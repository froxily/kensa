import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Dev and preview servers bind to loopback only; /api is proxied to the local backend.
// KENSA_API_PROXY lets the end-to-end tests point the dev server at their own backend.
const apiTarget = process.env.KENSA_API_PROXY ?? "http://127.0.0.1:8000";

// Mode "replay" builds the static replay demo: recorded runs (frontend/replay/recording.json)
// ship next to index.html, paths are relative so any static host works, and nothing is proxied.
export default defineConfig(({ mode }) => {
  const replay = mode === "replay";
  return {
    plugins: [react(), tailwindcss()],
    base: replay ? "./" : "/",
    publicDir: replay ? "replay" : false,
    build: { outDir: replay ? "dist-replay" : "dist" },
    server: {
      host: "127.0.0.1",
      port: 5173,
      strictPort: true,
      proxy: replay ? undefined : { "/api": { target: apiTarget } },
    },
    // A normal preview inherits the /api proxy; the replay preview must not reach any backend.
    preview: {
      host: "127.0.0.1",
      port: replay ? 4174 : 4173,
      strictPort: true,
      proxy: replay ? {} : undefined,
    },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      include: ["src/**/*.test.{ts,tsx}"],
      css: false,
    },
  };
});
