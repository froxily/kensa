import { Alert } from "../../../components/ui/Alert";
import { Badge } from "../../../components/ui/Badge";
import { Spinner } from "../../../components/ui/Spinner";
import { label, useLocale, useStrings } from "../../../i18n";
import { IS_REPLAY } from "../../../lib/api/mode";
import { formatNumber } from "../../../lib/format";
import { useChanges } from "../hooks";
import type { EvidenceItem } from "../types";

export function ChangesPanel({
  investigationId,
  evidence,
  onShowEvidence,
}: {
  investigationId: string;
  evidence: EvidenceItem[];
  onShowEvidence: (label: string) => void;
}) {
  const strings = useStrings();
  const c = strings.changes;
  const { locale } = useLocale();
  const query = useChanges(investigationId);
  if (query.isPending) return <Spinner label={strings.common.loading} />;
  if (query.isError)
    return (
      <Alert tone="danger" title={strings.common.unexpectedError}>
        <p>{query.error.message}</p>
      </Alert>
    );
  const data = query.data;
  if (!data) return null;
  return (
    <section
      aria-labelledby="changes-title"
      className="space-y-4 rounded-lg border border-zinc-200 p-5 dark:border-zinc-800"
    >
      <h2 id="changes-title" className="text-lg font-semibold">
        {c.title}
      </h2>
      {IS_REPLAY && <p className="text-sm font-medium">{c.replaySynthetic}</p>}
      <p className="text-sm">{c.disclaimer}</p>
      <Badge tone={data.comparability === "comparable" ? "success" : "warning"}>
        {c.comparability[data.comparability]}
      </Badge>
      <ul className="list-disc pl-5 text-sm">
        {data.reasons.map((reason, i) => (
          <li key={i}>{reason}</li>
        ))}
      </ul>
      {data.factors.length > 0 && (
        <div>
          <h3 className="font-semibold">{c.factors}</h3>
          <ul className="space-y-2">
            {data.factors.map((factor, i) => (
              <li key={i} className="text-sm">
                <span className="font-medium">{label(c.factorNames, factor.name)}</span>{" "}
                <Badge tone={factor.state === "unknown" ? "warning" : "neutral"}>
                  {c.states[factor.state]}
                </Badge>{" "}
                {factor.detail}
              </li>
            ))}
          </ul>
        </div>
      )}
      {data.unverified.length > 0 && (
        <div>
          <h3 className="font-semibold">{c.unverified}</h3>
          <ul className="list-disc pl-5 text-sm">
            {data.unverified.map((item, i) => (
              <li key={i}>{label(c.unverifiedFactors, item)}</li>
            ))}
          </ul>
        </div>
      )}
      {data.suspects.length > 0 && (
        <div>
          <h3 className="font-semibold">{c.suspects}</h3>
          <ol className="space-y-3">
            {[...data.suspects]
              .sort((a, b) => a.rank - b.rank)
              .map((suspect, i) => {
                const target = evidence.find((item) => item.document_id === suspect.document_id);
                return (
                  <li key={i} className="space-y-1 text-sm">
                    <p>
                      <span className="font-mono break-all">
                        {suspect.rank}. {suspect.path}
                      </span>{" "}
                      · {label(c.kinds, suspect.change_kind)}{" "}
                      <Badge tone={suspect.status === "correlated" ? "info" : "neutral"}>
                        {c.statuses[suspect.status]}
                      </Badge>{" "}
                      · {c.score}: {formatNumber(suspect.score, locale)}
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {Object.entries(suspect.signals).map(([name, value]) => (
                        <Badge key={name}>
                          {label(c.signals, name)}: {formatNumber(value, locale)}
                        </Badge>
                      ))}
                    </div>
                    {suspect.document_id &&
                      (target ? (
                        <button
                          type="button"
                          className="text-sky-700 underline dark:text-sky-400"
                          onClick={() => {
                            onShowEvidence(target.label);
                          }}
                        >
                          {c.diff}
                        </button>
                      ) : (
                        <p>{c.diff}</p>
                      ))}
                  </li>
                );
              })}
          </ol>
        </div>
      )}
      {data.truncated && <Alert tone="warning" title={c.truncated} />}
    </section>
  );
}
