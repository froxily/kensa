import { Link } from "react-router";

import { Alert } from "../components/ui/Alert";
import { buttonPrimary } from "../components/ui/button";
import { Spinner } from "../components/ui/Spinner";
import { ServiceStatusPanel } from "../features/health/ServiceStatusPanel";
import { InvestigationList } from "../features/investigations/components/InvestigationList";
import { useInvestigations } from "../features/investigations/hooks";
import { useStrings } from "../i18n";
import { IS_REPLAY } from "../lib/api/mode";

export function OverviewPage() {
  const strings = useStrings();
  const { data, isPending, isError, error, refetch } = useInvestigations();

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">{strings.overview.title}</h1>
        <Link to="/investigations/new" className={buttonPrimary}>
          {strings.nav.newInvestigation}
        </Link>
      </div>

      <section aria-labelledby="recent-title" className="space-y-3">
        <h2 id="recent-title" className="text-base font-semibold">
          {strings.overview.recent}
        </h2>
        {isPending && <Spinner label={strings.common.loading} />}
        {isError && (
          <Alert tone="danger" title={strings.common.unexpectedError} urgent>
            <p>{error.message}</p>
            <button type="button" className="mt-2 underline" onClick={() => void refetch()}>
              {strings.common.retry}
            </button>
          </Alert>
        )}
        {data?.items.length === 0 && (
          <div className="rounded-lg border border-dashed border-zinc-300 p-8 text-center dark:border-zinc-700">
            <p className="text-base font-semibold">{strings.overview.emptyTitle}</p>
            <p className="mx-auto mt-2 max-w-prose text-sm text-zinc-600 dark:text-zinc-400">
              {strings.overview.emptyBody}
            </p>
            <Link to="/investigations/new" className={`${buttonPrimary} mt-4`}>
              {strings.overview.start}
            </Link>
          </div>
        )}
        {data && data.items.length > 0 && <InvestigationList items={data.items} />}
      </section>

      {!IS_REPLAY && <ServiceStatusPanel />}
    </div>
  );
}
