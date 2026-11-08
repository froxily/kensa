import { defineConfig } from "vite";

const origin = process.env.PUBLIC_ORIGIN;
if (!origin) {
  throw new Error("PUBLIC_ORIGIN is required to build canonical URLs");
}

export default defineConfig({
  define: {
    __PUBLIC_ORIGIN__: JSON.stringify(origin),
  },
});
