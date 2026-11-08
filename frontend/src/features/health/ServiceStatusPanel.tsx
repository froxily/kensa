import { useStrings } from "../../i18n";
import type { ComponentStatus } from "./api";
import { useHealth } from "./useHealth";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 py-2">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right font-mono text-sm">{value}</dd>
    </div>
  );
}

export function ServiceStatusPanel() {
  const strings = useStrings();
  const statusText = (status: ComponentStatus): string => strings.health.status[status];
  const { data, isPending, isError, refetch, isFetching } = useHealth();

  return (
    <section
      aria-labelledby="service-status-title"
      className="rounded-lg border border-zinc-200 p-5 dark:border-zinc-800"
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 id="service-status-title" className="text-base font-semibold">
          {strings.health.panelTitle}
        </h2>
        <button
          type="button"
          onClick={() => void refetch()}
          disabled={isFetching}
          className="rounded-md border border-zinc-300 px-3 py-1 text-sm hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-900"
        >
          {strings.health.retry}
        </button>
      </div>

      {isPending && <p className="text-sm text-muted">{strings.health.checking}</p>}

      {isError && (
        <div className="text-sm">
          <p className="font-medium text-rose-600 dark:text-rose-400">
            {strings.health.unreachable}
          </p>
          <p className="mt-1 text-muted">{strings.health.unreachableHelp}</p>
        </div>
      )}

      {data && (
        <dl className="divide-y divide-zinc-200 text-sm dark:divide-zinc-800">
          <Row label={strings.health.database} value={statusText(data.database.status)} />
          <Row label={strings.health.pgvector} value={data.database.pgvector_version ?? "—"} />
          <Row
            label={strings.health.model}
            value={`${data.ollama.model} · ${statusText(data.ollama.status)}`}
          />
          <Row label={strings.health.provider} value={data.inference_provider} />
          <Row label={strings.health.version} value={data.version} />
        </dl>
      )}
    </section>
  );
}
