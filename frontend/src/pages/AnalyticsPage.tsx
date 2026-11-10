import { useState, type ReactNode } from "react";
import { Link } from "react-router";
import { Alert } from "../components/ui/Alert";
import { Spinner } from "../components/ui/Spinner";
import { useDashboard } from "../features/analytics/hooks";
import { TrackingPanel } from "../features/tracking/TrackingPanel";
import { format, label, useLocale, useStrings } from "../i18n";
import { IS_REPLAY } from "../lib/api/mode";
import { formatDateTime, formatNumber, formatPercent } from "../lib/format";

function Table({ name, headers, rows }: { name: string; headers: string[]; rows: ReactNode[][] }) {
  return (
    <div className="max-w-full overflow-x-auto" tabIndex={0} role="region" aria-label={name}>
      <table className="w-full text-left text-sm">
        <thead>
          <tr>
            {headers.map((h) => (
              <th className="p-2" scope="col" key={h}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr className="border-t border-zinc-300 dark:border-zinc-700" key={i}>
              {row.map((cell, j) => (
                <td className="p-2" key={j}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function AnalyticsPage() {
  const s = useStrings();
  const a = s.analytics;
  const { locale } = useLocale();
  const [filters, setFilters] = useState({
    days: 30,
    repository: "",
    workflow: "",
    include_all_origins: false,
  });
  const query = useDashboard(filters);
  const d = query.data;
  const n = (v: number) => formatNumber(v, locale);
  const p = (v: number | null) => (v === null ? "—" : formatPercent(v));
  const value = (v: number | null) => (v === null ? "—" : n(v));
  const trendMax = Math.max(
    1,
    ...(d?.trends.flatMap((x) => [x.runs, x.failed_runs, x.investigations]) ?? []),
  );
  const catMax = Math.max(1, ...(d?.categories.map((x) => x.investigations) ?? []));
  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-semibold">{a.title}</h1>
      <form
        className="flex flex-wrap items-end gap-4"
        onSubmit={(e) => {
          e.preventDefault();
        }}
      >
        <label className="grid gap-1">
          {a.range}
          <select
            className="rounded border border-zinc-400 bg-transparent p-2"
            value={filters.days}
            onChange={(e) => {
              setFilters({ ...filters, days: Number(e.target.value) });
            }}
          >
            {[7, 30, 90, 365].map((x) => (
              <option value={x} key={x}>
                {format(a.days, { count: x })}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1">
          {a.repository}
          <select
            className="max-w-60 rounded border border-zinc-400 bg-transparent p-2"
            value={filters.repository}
            onChange={(e) => {
              setFilters({ ...filters, repository: e.target.value });
            }}
          >
            <option value="">{a.all}</option>
            {d?.options.repositories.map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
        </label>
        <label className="grid gap-1">
          {a.workflow}
          <select
            className="max-w-60 rounded border border-zinc-400 bg-transparent p-2"
            value={filters.workflow}
            onChange={(e) => {
              setFilters({ ...filters, workflow: e.target.value });
            }}
          >
            <option value="">{a.all}</option>
            {d?.options.workflows.map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={filters.include_all_origins}
            onChange={(e) => {
              setFilters({ ...filters, include_all_origins: e.target.checked });
            }}
          />
          {a.include}
        </label>
      </form>
      <p className="text-sm text-muted">{a.note}</p>
      {IS_REPLAY && <p className="text-sm font-medium">{a.replayNote}</p>}
      {query.isPending && <Spinner label={s.common.loading} />}
      {query.isError && (
        <Alert tone="danger" title={s.common.unexpectedError}>
          {query.error.message}
        </Alert>
      )}
      {d && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
            {[
              [a.runs, n(d.summary.runs)],
              [a.failed, n(d.summary.failed_runs)],
              [a.rate, p(d.summary.failure_rate)],
              [a.investigations, n(d.summary.investigations)],
              [a.corroborated, n(d.summary.corroborated)],
              [a.median, value(d.summary.latency_p50_seconds)],
              [a.p95, value(d.summary.latency_p95_seconds)],
              [a.recurring, value(d.summary.recurring_failures)],
              [a.quality, n(d.summary.open_quality_findings)],
            ].map(([k, v]) => (
              <div className="rounded border border-zinc-300 p-3 dark:border-zinc-700" key={k}>
                <p className="text-sm text-muted">{k}</p>
                <p className="text-xl font-semibold">{v}</p>
              </div>
            ))}
          </div>
          {d.summary.runs === 0 && d.summary.investigations === 0 && <p>{a.empty}</p>}
          <section className="space-y-3">
            <h2 className="text-lg font-semibold">{a.trend}</h2>
            <figure>
              <figcaption id="trend-caption">
                {a.trendCaption} ({format(a.days, { count: filters.days })})
              </figcaption>
              <svg
                role="img"
                aria-labelledby="trend-caption"
                viewBox={`0 0 ${String(Math.max(300, d.trends.length * 12))} 120`}
                className="h-40 w-full"
                preserveAspectRatio="none"
              >
                {d.trends.map((x, i) => (
                  <g key={x.day}>
                    <rect
                      x={i * 12}
                      y={110 - (x.runs / trendMax) * 100}
                      width="4"
                      height={(x.runs / trendMax) * 100}
                      className="fill-sky-700 dark:fill-sky-400"
                    />
                    <rect
                      x={i * 12 + 4}
                      y={110 - (x.failed_runs / trendMax) * 100}
                      width="4"
                      height={(x.failed_runs / trendMax) * 100}
                      className="fill-rose-700 dark:fill-rose-400"
                    />
                    <rect
                      x={i * 12 + 8}
                      y={110 - (x.investigations / trendMax) * 100}
                      width="3"
                      height={(x.investigations / trendMax) * 100}
                      className="fill-amber-700 dark:fill-amber-400"
                    />
                  </g>
                ))}
              </svg>
              <ul className="flex flex-wrap gap-x-4 text-sm">
                <li>
                  <span aria-hidden="true" className="text-sky-700 dark:text-sky-400">
                    ■
                  </span>{" "}
                  {a.runs}
                </li>
                <li>
                  <span aria-hidden="true" className="text-rose-700 dark:text-rose-400">
                    ■
                  </span>{" "}
                  {a.failed}
                </li>
                <li>
                  <span aria-hidden="true" className="text-amber-700 dark:text-amber-400">
                    ■
                  </span>{" "}
                  {a.investigations}
                </li>
              </ul>
              {d.trends.length > 0 && (
                <p className="text-sm text-muted">
                  {d.trends[0]?.day} – {d.trends.at(-1)?.day}
                </p>
              )}
            </figure>
            <details>
              <summary>{a.table}</summary>
              <Table
                name={a.trend}
                headers={[a.day, a.runs, a.failed, a.investigations, a.corroborated]}
                rows={d.trends.map((x) => [
                  x.day,
                  n(x.runs),
                  n(x.failed_runs),
                  n(x.investigations),
                  n(x.corroborated),
                ])}
              />
            </details>
          </section>
          <section className="space-y-3">
            <h2 className="text-lg font-semibold">{a.categories}</h2>
            <figure>
              <figcaption id="category-caption">
                {a.categories}: {a.investigations}, {a.corroborated}
              </figcaption>
              <svg
                role="img"
                aria-labelledby="category-caption"
                viewBox={`0 0 300 ${String(Math.max(30, d.categories.length * 30))}`}
                className="w-full"
                style={{ height: Math.max(30, d.categories.length * 30) }}
              >
                {d.categories.map((x, i) => (
                  <g key={x.category}>
                    <rect
                      x="0"
                      y={i * 30}
                      width={(x.investigations / catMax) * 300}
                      height="20"
                      className="fill-sky-700 dark:fill-sky-400"
                    />
                    <rect
                      x="0"
                      y={i * 30}
                      width={(x.corroborated / catMax) * 300}
                      height="20"
                      className="fill-emerald-700 dark:fill-emerald-400"
                    />
                  </g>
                ))}
              </svg>
              <ul className="text-sm">
                {d.categories.map((x) => (
                  <li key={x.category}>
                    {label(s.categories, x.category)}: {n(x.investigations)} · {a.corroborated}:{" "}
                    {n(x.corroborated)}
                  </li>
                ))}
              </ul>
            </figure>
            <details>
              <summary>{a.table}</summary>
              <Table
                name={a.categories}
                headers={[a.categories, a.investigations, a.corroborated]}
                rows={d.categories.map((x) => [
                  label(s.categories, x.category),
                  n(x.investigations),
                  n(x.corroborated),
                ])}
              />
            </details>
          </section>
          <section>
            <h2 className="text-lg font-semibold">{a.workflows}</h2>
            <Table
              name={a.workflows}
              headers={[a.repository, a.workflow, a.runs, a.failed, a.rate, a.investigations]}
              rows={d.workflows.map((x) => [
                x.repository,
                x.workflow,
                n(x.runs),
                n(x.failed_runs),
                p(x.failure_rate),
                n(x.investigations),
              ])}
            />
          </section>
          <section>
            <h2 className="text-lg font-semibold">{a.recurring}</h2>
            {!d.history_matching ? (
              <p>{a.recurringOff}</p>
            ) : (
              <Table
                name={a.recurring}
                headers={[a.categories, a.subject, a.occurrences, a.lastSeen, a.links]}
                rows={d.recurring.map((x) => [
                  label(s.categories, x.category),
                  x.subject || x.template,
                  n(x.occurrences),
                  formatDateTime(x.last_seen, locale),
                  <span className="flex flex-wrap gap-2">
                    {x.investigation_ids.slice(0, 5).map((id) => (
                      <Link
                        className="underline"
                        key={id}
                        to={`/investigations/${encodeURIComponent(id)}`}
                      >
                        {id}
                      </Link>
                    ))}
                  </span>,
                ])}
              />
            )}
          </section>
          <section>
            <h2 className="text-lg font-semibold">{a.freshness}</h2>
            <Table
              name={a.freshness}
              headers={[a.repository, a.lag]}
              rows={d.freshness.map((x) => [x.repository, value(x.lag_hours)])}
            />
          </section>
          <section>
            <h2 className="text-lg font-semibold">{a.dataQuality}</h2>
            <Table
              name={a.dataQuality}
              headers={[a.check, a.severity, a.open]}
              rows={d.quality.map((x) => [
                label(a.checks, x.check),
                label(a.severities, x.severity),
                n(x.open),
              ])}
            />
          </section>
        </>
      )}
      <TrackingPanel />
    </div>
  );
}
