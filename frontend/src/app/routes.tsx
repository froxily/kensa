import type { RouteObject } from "react-router";

import { InvestigationPage } from "../pages/InvestigationPage";
import { NewInvestigationPage } from "../pages/NewInvestigationPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { OverviewPage } from "../pages/OverviewPage";
import { AppShell } from "./AppShell";

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <OverviewPage /> },
      { path: "investigations/new", element: <NewInvestigationPage /> },
      { path: "investigations/:id", element: <InvestigationPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
