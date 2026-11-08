import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider, createBrowserRouter, createHashRouter } from "react-router";

import { routes } from "./app/routes";
import { applyTheme, readPreference } from "./features/theme/theme";
import { LocaleProvider } from "./i18n";
import { applyLocale, readLocale } from "./i18n/preference";
import { IS_REPLAY } from "./lib/api/mode";
import "./index.css";

// Apply the theme and language before first paint to avoid a flash of the wrong one.
applyTheme(readPreference());
const locale = readLocale();
applyLocale(locale);

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});
// The replay build is static: hash URLs let deep links work on any file host.
const router = IS_REPLAY ? createHashRouter(routes) : createBrowserRouter(routes);

const container = document.getElementById("root");
if (!container) throw new Error("Root element #root not found");

createRoot(container).render(
  <StrictMode>
    <LocaleProvider initial={locale}>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </LocaleProvider>
  </StrictMode>,
);
