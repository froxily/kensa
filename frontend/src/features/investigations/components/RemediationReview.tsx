import { useState } from "react";

import { Alert } from "../../../components/ui/Alert";
import { Badge } from "../../../components/ui/Badge";
import { buttonPrimary, buttonSecondary } from "../../../components/ui/button";
import { format, useLocale, useStrings } from "../../../i18n";
import { IS_REPLAY } from "../../../lib/api/mode";
import { formatDateTime } from "../../../lib/format";
import { useDecideInvestigation } from "../hooks";
import type {
  ApprovalDecision,
  Decision,
  InvestigationStatus,
  RemediationProposal,
} from "../types";

interface Props {
  investigationId: string;
  status: InvestigationStatus;
  proposals: RemediationProposal[];
  decision: ApprovalDecision | null;
}

function sameText(a: string, b: string): boolean {
  return a.trim().replace(/\.$/, "").toLowerCase() === b.trim().replace(/\.$/, "").toLowerCase();
}

export function RemediationReview({ investigationId, status, proposals, decision }: Props) {
  const strings = useStrings();
  const { locale } = useLocale();
  const r = strings.review;
  const [note, setNote] = useState("");
  const mutation = useDecideInvestigation(investigationId);
  const submit = (choice: Decision) => {
    mutation.mutate({ decision: choice, ...(note.trim() ? { note } : {}) });
  };

  return (
    <section
      aria-labelledby="review-title"
      className="space-y-5 rounded-lg border border-zinc-200 p-5 dark:border-zinc-800"
    >
      <h2 id="review-title" className="text-lg font-semibold">
        {r.title}
      </h2>
      <p className="text-sm">{r.intro}</p>
      <ol className="space-y-4">
        {proposals.map((proposal) => (
          <li
            key={proposal.id}
            className="space-y-3 rounded-lg border border-zinc-200 p-4 dark:border-zinc-800"
          >
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-semibold">{proposal.title}</h3>
              <Badge>{r.origin[proposal.origin]}</Badge>
              <Badge
                tone={
                  proposal.status === "approved"
                    ? "success"
                    : proposal.status === "rejected" || proposal.status === "withdrawn"
                      ? "danger"
                      : "neutral"
                }
              >
                {r.status[proposal.status]}
              </Badge>
            </div>
            {proposal.status === "withdrawn" && (
              <Alert tone="warning" title={r.withdrawnTitle}>
                <p>{proposal.withdrawn_reason}</p>
                {proposal.withdrawn_at && (
                  <p className="text-xs">
                    {format(r.withdrawnOn, { date: formatDateTime(proposal.withdrawn_at, locale) })}
                  </p>
                )}
              </Alert>
            )}
            {/* The model sometimes repeats its title as the action, or the action as the
                rationale; each text is shown once. */}
            {!sameText(proposal.action, proposal.title) && (
              <p className="text-sm">{proposal.action}</p>
            )}
            {proposal.rationale &&
              !sameText(proposal.rationale, proposal.action) &&
              !sameText(proposal.rationale, proposal.title) && (
                <p className="text-sm">{proposal.rationale}</p>
              )}
            {proposal.target_path && (
              <p className="break-all font-mono text-sm">{proposal.target_path}</p>
            )}
            {proposal.diff !== null && (
              <pre className="whitespace-pre-wrap break-all rounded bg-zinc-100 p-3 font-mono text-xs dark:bg-zinc-900">
                {proposal.diff.split("\n").map((line, index) => {
                  const added = line.startsWith("+") && !line.startsWith("+++");
                  const removed = line.startsWith("-") && !line.startsWith("---");
                  return (
                    <span
                      key={index}
                      className={`block ${added ? "text-emerald-800 dark:text-emerald-300" : removed ? "text-rose-800 dark:text-rose-300" : line.startsWith("@@") ? "text-muted" : ""}`}
                    >
                      {added && <span className="sr-only">{r.added} </span>}
                      {removed && <span className="sr-only">{r.removed} </span>}
                      {line || " "}
                    </span>
                  );
                })}
              </pre>
            )}
            {proposal.risks.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-muted">{r.risks}</h4>
                <ul className="list-disc pl-5 text-sm">
                  {proposal.risks.map((risk, index) => (
                    <li key={index}>{risk}</li>
                  ))}
                </ul>
              </div>
            )}
            {proposal.flags.length > 0 && (
              <ul className="flex flex-wrap gap-2">
                {proposal.flags.map((flag, index) => (
                  <li key={index}>
                    <span className="rounded bg-amber-100 px-1 text-xs text-amber-900 dark:bg-amber-900 dark:text-amber-100">
                      {format(r.flagged, { flag })}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {proposal.validation_steps.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-muted">{r.validation}</h4>
                <ol className="list-decimal pl-5 text-sm">
                  {proposal.validation_steps.map((step, index) => (
                    <li key={index}>{step}</li>
                  ))}
                </ol>
              </div>
            )}
          </li>
        ))}
      </ol>
      {decision && (
        <Alert
          tone={decision.decision === "approved" ? "success" : "neutral"}
          title={format(decision.decision === "approved" ? r.approvedOn : r.rejectedOn, {
            date: formatDateTime(decision.created_at, locale),
          })}
        >
          {IS_REPLAY && <p className="font-semibold">{strings.replay.decisionNotSaved}</p>}
          {decision.note && <p className="whitespace-pre-wrap">{decision.note}</p>}
          {decision.decision === "approved" && <p>{r.notApplied}</p>}
          {(status === "queued" || status === "running") && <p>{r.resuming}</p>}
        </Alert>
      )}
      {status === "awaiting_approval" && decision === null && (
        <div className="space-y-3">
          <label htmlFor="review-note" className="block text-sm font-medium">
            {r.note}
          </label>
          <textarea
            id="review-note"
            maxLength={1000}
            value={note}
            onChange={(event) => {
              setNote(event.target.value);
            }}
            className="w-full rounded-md border border-zinc-300 p-2 dark:border-zinc-700"
          />
          {mutation.isError && (
            <Alert tone="danger" title={r.error} urgent>
              <p>{mutation.error.message}</p>
            </Alert>
          )}
          {IS_REPLAY && (
            <p
              id="review-replay-note"
              className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-800 dark:bg-amber-950"
            >
              {strings.replay.decisionTemporary}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className={buttonPrimary}
              disabled={mutation.isPending}
              aria-describedby={IS_REPLAY ? "review-replay-note" : undefined}
              onClick={() => {
                submit("approved");
              }}
            >
              {r.approve}
            </button>
            <button
              type="button"
              className={buttonSecondary}
              aria-describedby={IS_REPLAY ? "review-replay-note" : undefined}
              disabled={mutation.isPending}
              onClick={() => {
                submit("rejected");
              }}
            >
              {r.reject}
            </button>
          </div>
          {mutation.isPending && (
            <p role="status" className="text-sm">
              {r.recording}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
