import { useState } from "react";
import { Link } from "react-router";
import { Alert } from "../../../components/ui/Alert";
import { Badge } from "../../../components/ui/Badge";
import { buttonPrimary } from "../../../components/ui/button";
import { Spinner } from "../../../components/ui/Spinner";
import { useLocale, useStrings } from "../../../i18n";
import { IS_REPLAY } from "../../../lib/api/mode";
import { formatDateTime, formatNumber } from "../../../lib/format";
import { useHistory, useSaveResolution } from "../hooks";
import { categoryLabel } from "../labels";
import type { History } from "../types";

type Match = History["similar"][number];

function MatchList({ items, headingId }: { items: Match[]; headingId: string }) {
  const strings = useStrings();
  const s = strings.similar;
  const { locale } = useLocale();
  return (
    <ul className="space-y-3" aria-labelledby={headingId}>
      {items.map((item) => (
        <li key={item.investigation_id} className="space-y-1 text-sm">
          <Link
            className="break-words text-sky-700 underline dark:text-sky-400"
            to={`/investigations/${encodeURIComponent(item.investigation_id)}`}
          >
            {item.title}
          </Link>
          <p>
            {formatDateTime(item.created_at, locale)} · {item.earlier ? s.earlier : s.later}
          </p>
          <div className="flex flex-wrap gap-2">
            <Badge tone={item.match === "same_failure" ? "info" : "neutral"}>
              {s.matches[item.match]}
            </Badge>
            <Badge
              tone={
                item.provenance === "human_confirmed"
                  ? "success"
                  : item.provenance === "verifier_corroborated"
                    ? "info"
                    : "neutral"
              }
            >
              {s.provenance[item.provenance]}
            </Badge>
          </div>
          <p>
            {s.diagnosis}: {categoryLabel(strings, item.diagnosis_category)}
          </p>
          {item.resolution && (
            <p className="whitespace-pre-wrap">
              {s.resolution}: {item.resolution}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}

export function HistoryPanel({ investigationId }: { investigationId: string }) {
  const strings = useStrings();
  const s = strings.similar;
  const { locale } = useLocale();
  const query = useHistory(investigationId);
  const mutation = useSaveResolution(investigationId);
  const [summary, setSummary] = useState("");
  if (query.isPending) return <Spinner label={strings.common.loading} />;
  if (query.isError)
    return (
      <Alert tone="danger" title={strings.common.unexpectedError}>
        <p>{query.error.message}</p>
      </Alert>
    );
  const primary = query.data.fingerprints.find((f) => f.role === "primary");
  // Only an exact fingerprint match is a recurrence; everything else is a similarity (D-057).
  const recurrences = query.data.similar.filter((item) => item.match === "same_failure");
  const similar = query.data.similar.filter((item) => item.match !== "same_failure");
  const resolution = mutation.data ?? query.data.resolution;
  return (
    <section
      aria-labelledby="history-title"
      className="space-y-4 rounded-lg border border-zinc-200 p-5 dark:border-zinc-800"
    >
      <h2 id="history-title" className="flex flex-wrap items-center gap-2 text-lg font-semibold">
        {s.title}
        <Badge tone="neutral">{s.experimental}</Badge>
      </h2>
      <p className="text-sm">{s.disclaimer}</p>
      <p className="text-sm">{query.data.matching ? s.experimentalNote : s.matchingOff}</p>
      {primary && (
        <p className="text-sm">
          {categoryLabel(strings, primary.category)} · {primary.subject || primary.template}
          {primary.kind === "exact" && primary.occurrences !== null && (
            <>
              {" "}
              · {s.occurrences}: {formatNumber(primary.occurrences, locale)}
            </>
          )}
        </p>
      )}
      {query.data.matching && primary?.kind === "approximate" && (
        <p className="text-sm">{s.approximate}</p>
      )}
      {query.data.matching && (
        <div className="space-y-2">
          <h3 id="history-recurrences" className="font-semibold">
            {s.recurrences}
          </h3>
          {recurrences.length > 0 ? (
            <MatchList items={recurrences} headingId="history-recurrences" />
          ) : (
            <p className="text-sm">{s.noRecurrence}</p>
          )}
        </div>
      )}
      {query.data.matching && similar.length > 0 && (
        <div className="space-y-2">
          <h3 id="history-similar" className="font-semibold">
            {s.similarTitle}
          </h3>
          <p className="text-sm">{s.similarNote}</p>
          <MatchList items={similar} headingId="history-similar" />
        </div>
      )}
      {resolution && (
        <div className="text-sm">
          <h3 className="font-semibold">{s.saved}</h3>
          <p className="whitespace-pre-wrap">{resolution.summary}</p>
        </div>
      )}
      <form
        className="space-y-2"
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate(summary.trim(), {
            onSuccess: () => {
              setSummary("");
            },
          });
        }}
      >
        <label htmlFor="resolution-summary" className="block text-sm font-medium">
          {s.question}
        </label>
        <textarea
          id="resolution-summary"
          className="w-full rounded-md border border-zinc-300 p-2 dark:border-zinc-700"
          minLength={3}
          maxLength={1000}
          value={summary}
          disabled={IS_REPLAY}
          onChange={(event) => {
            setSummary(event.target.value);
          }}
        />
        {IS_REPLAY && <p className="text-sm">{strings.replay.unsupported}</p>}
        {mutation.isError && (
          <Alert tone="danger" title={s.error}>
            <p>{mutation.error.message}</p>
          </Alert>
        )}
        <button
          className={buttonPrimary}
          type="submit"
          disabled={IS_REPLAY || mutation.isPending || summary.trim().length < 3}
        >
          {s.submit}
        </button>
      </form>
    </section>
  );
}
