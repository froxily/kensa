import { NavLink, Outlet } from "react-router";

import { HealthIndicator } from "../features/health/HealthIndicator";
import { LanguageSelect } from "../features/language/LanguageSelect";
import { ReplayBanner } from "../features/replay/ReplayBanner";
import { ReplayStatus } from "../features/replay/ReplayStatus";
import { ThemeSelect } from "../features/theme/ThemeSelect";
import { useStrings } from "../i18n";
import { IS_REPLAY } from "../lib/api/mode";

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium ${
    isActive
      ? "bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-50"
      : "text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
  }`;

export function AppShell() {
  const strings = useStrings();
  return (
    <div className="min-h-dvh">
      {/* Moves focus itself: in the replay build "#main" would be read as a route. */}
      <a
        href="#main"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("main")?.focus();
        }}
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-10 focus:rounded-md focus:bg-sky-700 focus:px-3 focus:py-2 focus:text-white"
      >
        {strings.app.skipToContent}
      </a>
      {IS_REPLAY && <ReplayBanner />}
      <header className="border-b border-zinc-200 dark:border-zinc-800">
        {/* One row from lg up; below that the controls wrap onto their own row, so a phone
            screen never scrolls sideways (checked by replay.spec.ts at 375 px). */}
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 lg:h-14 lg:flex-nowrap lg:py-0">
          <div className="flex shrink-0 items-baseline gap-2 whitespace-nowrap">
            <span className="text-lg font-semibold tracking-tight">{strings.app.name}</span>
            <span aria-hidden="true" className="text-sm text-muted">
              検査
            </span>
          </div>
          <nav aria-label={strings.nav.label} className="flex flex-wrap gap-1">
            <NavLink to="/" end className={navLinkClass}>
              {strings.nav.overview}
            </NavLink>
            <NavLink to="/investigations/new" className={navLinkClass}>
              {strings.nav.newInvestigation}
            </NavLink>
            <NavLink to="/analytics" className={navLinkClass}>
              {strings.nav.analytics}
            </NavLink>
          </nav>
          <div className="flex w-full flex-wrap items-center gap-3 lg:ml-auto lg:w-auto">
            {IS_REPLAY ? <ReplayStatus /> : <HealthIndicator />}
            <LanguageSelect />
            <ThemeSelect />
          </div>
        </div>
      </header>
      <main id="main" tabIndex={-1} className="mx-auto max-w-6xl px-4 py-8 focus:outline-none">
        <Outlet />
      </main>
    </div>
  );
}
