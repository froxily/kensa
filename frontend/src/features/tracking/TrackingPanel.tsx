import { useState } from "react";
import { Alert } from "../../components/ui/Alert";
import { buttonPrimary, buttonSecondary } from "../../components/ui/button";
import { Spinner } from "../../components/ui/Spinner";
import { format, label, useLocale, useStrings } from "../../i18n";
import { IS_REPLAY } from "../../lib/api/mode";
import { formatDateTime, formatNumber } from "../../lib/format";
import { useTracking } from "./hooks";

export function TrackingPanel() {
  const s = useStrings();
  const { locale } = useLocale();
  const { repositories, track, sync, forget } = useTracking();
  const [url, setUrl] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const error = track.error ?? sync.error ?? forget.error;
  return (
    <section className="space-y-3" aria-labelledby="tracking-title">
      <h2 id="tracking-title" className="text-lg font-semibold">
        {s.tracking.title}
      </h2>
      <p>{s.tracking.syncHelp}</p>
      {IS_REPLAY && <p>{s.replay.unsupported}</p>}
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          track.mutate(url, {
            onSuccess: () => {
              setUrl("");
            },
          });
        }}
      >
        <label className="grid gap-1">
          {s.tracking.url}
          <input
            className="rounded border border-zinc-400 bg-transparent p-2"
            type="url"
            required
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
            }}
            disabled={IS_REPLAY}
          />
        </label>
        <button className={buttonPrimary} disabled={IS_REPLAY || track.isPending}>
          {s.tracking.track}
        </button>
      </form>
      {repositories.isPending && <Spinner label={s.common.loading} />}{" "}
      {repositories.isError && (
        <Alert tone="danger" title={s.common.unexpectedError}>
          {repositories.error.message}
        </Alert>
      )}{" "}
      {error && (
        <Alert tone="danger" title={s.common.unexpectedError}>
          {error.message}
        </Alert>
      )}
      {forget.data && (
        <div role="status">
          <p>{s.tracking.deleted}</p>
          <ul>
            {Object.entries(forget.data).map(([key, value]) => (
              <li key={key}>
                {key}: {formatNumber(value, locale)}
              </li>
            ))}
          </ul>
        </div>
      )}
      <ul className="space-y-4">
        {repositories.data?.map((r) => {
          const name = `${r.owner}/${r.repo}`;
          return (
            <li
              key={r.id}
              className="space-y-2 rounded border border-zinc-300 p-4 dark:border-zinc-700"
            >
              <h3 className="font-semibold break-all">{name}</h3>
              <p>
                {s.tracking.lastSync}:{" "}
                {r.last_sync_at ? formatDateTime(r.last_sync_at, locale) : "—"} ·{" "}
                {s.tracking.complete}:{" "}
                {r.complete_through ? formatDateTime(r.complete_through, locale) : "—"}
              </p>
              <p>
                {s.analytics.runs}: {formatNumber(r.runs, locale)} · {s.analytics.failed}:{" "}
                {formatNumber(r.failed_runs, locale)}
              </p>
              <p>
                {s.tracking.batch}:{" "}
                {r.last_batch ? label(s.tracking.statuses, r.last_batch.status) : "—"}{" "}
                {r.last_batch &&
                  ["failed", "rate_limited"].includes(r.last_batch.status) &&
                  r.last_batch.message}
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  className={buttonSecondary}
                  type="button"
                  disabled={IS_REPLAY || r.syncing || sync.isPending}
                  onClick={() => {
                    sync.mutate(r.id);
                  }}
                >
                  {s.tracking.sync}
                </button>
                <button
                  className={buttonSecondary}
                  type="button"
                  disabled={IS_REPLAY}
                  onClick={() => {
                    setSelected(r.id);
                    setConfirmation("");
                    forget.reset();
                  }}
                >
                  {s.tracking.forget}
                </button>
              </div>
              {selected === r.id && (
                <form
                  className="space-y-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (confirmation === name)
                      forget.mutate(
                        { id: r.id, confirm: confirmation },
                        {
                          onSuccess: () => {
                            setSelected(null);
                          },
                        },
                      );
                  }}
                >
                  <p>{s.tracking.warning}</p>
                  <label className="grid gap-1">
                    {format(s.tracking.confirm, { name })}
                    <input
                      className="rounded border border-zinc-400 bg-transparent p-2"
                      value={confirmation}
                      onChange={(e) => {
                        setConfirmation(e.target.value);
                      }}
                    />
                  </label>
                  <div className="flex gap-2">
                    <button
                      className={buttonPrimary}
                      disabled={confirmation !== name || forget.isPending}
                    >
                      {s.tracking.forget}
                    </button>
                    <button
                      className={buttonSecondary}
                      type="button"
                      onClick={() => {
                        setSelected(null);
                      }}
                    >
                      {s.tracking.cancel}
                    </button>
                  </div>
                </form>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
