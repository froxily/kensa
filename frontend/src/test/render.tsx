import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router";

import { routes } from "../app/routes";
import { LocaleProvider } from "../i18n";
import type { Locale } from "../i18n";

export function renderApp(path = "/", locale: Locale = "en") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const view = render(
    <LocaleProvider initial={locale}>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </LocaleProvider>,
  );
  return { ...view, router, queryClient };
}

export { jsonResponse } from "./mockApi";
