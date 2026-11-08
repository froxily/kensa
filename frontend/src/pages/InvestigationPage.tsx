import { useMemo, useState } from "react";
import { Link, useParams } from "react-router";

import { Alert } from "../components/ui/Alert";
import { Badge } from "../components/ui/Badge";
import { buttonPrimary } from "../components/ui/button";
import { Spinner } from "../components/ui/Spinner";
import { StatusBadge } from "../features/investigations/components/Badges";
import { GitHubRunCard } from "../features/investigations/components/GitHubRunCard";
import { DiagnosisReport } from "../features/investigations/components/DiagnosisReport";
import { RemediationReview } from "../features/investigations/components/RemediationReview";
import { EvidenceList } from "../features/investigations/components/EvidenceList";
import { evidenceElementId } from "../features/investigations/evidence";
import { LogViewer } from "../features/investigations/components/LogViewer";
import { Timeline } from "../features/investigations/components/Timeline";
import {
  useAgentEvents,
  useInvestigation,
  useRetryInvestigation,
} from "../features/investigations/hooks";
import { useLocale, useStrings } from "../i18n";
import { IS_REPLAY } from "../lib/api/mode";
import { formatDateTime } from "../lib/format";

export function InvestigationPage() {
  const strings = useStrings();
  const { locale } = useLocale();
  const { id = "" } = useParams();
  const i = strings.investigation;
  const { data, isPending, isError, error } = useInvestigation(id);
  const timeline = useAgentEvents(id, data?.status);
  const retry = useRetryInvestigation(id);
  const [focusLine, setFocusLine] = useState<number | null>(null);

  const marked = useMemo(() => {
    const lines = new Set<number>(data?.signatures.map((s) => s.line_number) ?? []);
    const elsewhere = new Set(
      data?.evidence.filter((e) => e.source_type !== "log").map((e) => e.label),
    );
    for (const citation of data?.diagnosis?.citations ?? []) {
      if (citation.valid && !elsewhere.has(citation.evidence_label)) {
        lines.add(citation.line_number);
      }
    }
    return lines;
  }, [data]);

  const showEvidence = (evidenceLabel: string) => {
    const card = window.document.getElementById(evidenceElementId(evidenceLabel));
    card?.scrollIntoView({ block: "center", behavior: "smooth" });
    card?.focus({ preventScroll: true });
  };

  if (isPending) return <Spinner label={strings.common.loading} />;
  if (isError) {
    const missing = "status" in error && error.status === 404;
    return (
      <Alert tone="danger" title={missing ? i.notFound : strings.common.unexpectedError} urgent>
        {!missing && <p>{error.message}</p>}
        <Link to="/" className="mt-2 inline-block underline">
          {i.back}
        </Link>
      </Alert>
    );
  }

  const document = data.documents[0];
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Link to="/" className="text-sm text-sky-700 hover:underline dark:text-sky-400">
          ← {i.back}
        </Link>
        <div className="flex flex-wrap items-start gap-3">
          <h1 className="min-w-0 flex-1 break-words text-xl font-semibold tracking-tight">
            {data.title}
          </h1>
          {IS_REPLAY && <Badge tone="warning">{strings.replay.badge}</Badge>}
          <StatusBadge status={data.status} />
        </div>
        <p className="text-xs text-muted">
          {i.provider}: {data.provider === "mock" ? i.rulesOnly : (data.model ?? data.provider)} ·{" "}
          {i.created} {formatDateTime(data.created_at, locale)}
        </p>
        {locale !== "en" && (
          <p className="text-xs text-muted">{strings.language.recordedInEnglish}</p>
        )}
      </div>

      {data.status === "failed" && (
        <Alert tone="danger" title={i.failedTitle} urgent>
          <p>{data.error_message}</p>
          <button
            type="button"
            className={`${buttonPrimary} mt-3`}
            disabled={retry.isPending}
            onClick={() => {
              retry.mutate();
            }}
          >
            {retry.isPending ? i.retrying : i.retry}
          </button>
        </Alert>
      )}
      {data.status === "queued" && data.error_code && (
        <Alert tone="warning" title={i.queuedRetry}>
          <p>{data.error_message}</p>
        </Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-6">
          {data.github_run && <GitHubRunCard run={data.github_run} />}
          {data.diagnosis && (
            <DiagnosisReport
              diagnosis={data.diagnosis}
              evidence={data.evidence}
              onShowLine={setFocusLine}
              onShowEvidence={showEvidence}
            />
          )}
          {(data.proposals.length > 0 || data.decision !== null) && (
            <RemediationReview
              investigationId={id}
              status={data.status}
              proposals={data.proposals}
              decision={data.decision}
            />
          )}
          {document && (
            <LogViewer
              investigationId={id}
              document={document}
              marked={marked}
              focusLine={focusLine}
            />
          )}
          <EvidenceList evidence={data.evidence} onShowLine={setFocusLine} />
        </div>
        <div className="min-w-0">
          <Timeline events={timeline.events} />
        </div>
      </div>
    </div>
  );
}
