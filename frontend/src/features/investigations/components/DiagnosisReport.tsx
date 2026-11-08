import { Alert } from "../../../components/ui/Alert";
import { format, useStrings } from "../../../i18n";
import type { Diagnosis, EvidenceItem } from "../types";
import { categoryLabel } from "../labels";
import { VerificationBadge } from "./Badges";

interface Props {
  diagnosis: Diagnosis;
  evidence: EvidenceItem[];
  onShowLine: (line: number) => void;
  /** Citations of repository files, docs or knowledge notes point at their evidence card. */
  onShowEvidence: (label: string) => void;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-muted">{title}</h3>
      <div className="mt-1 text-sm">{children}</div>
    </div>
  );
}

export function DiagnosisReport({ diagnosis, evidence, onShowLine, onShowEvidence }: Props) {
  const strings = useStrings();
  const r = strings.report;
  const sources = new Map(evidence.map((item) => [item.label, item]));
  const unknown = diagnosis.verification_status === "not_established";
  const validCitations = diagnosis.citations.filter((c) => c.valid).length;
  const flagged = new Set(
    diagnosis.verification_notes
      .map((note) => /^Fix (\d+) flagged/.exec(note)?.[1])
      .filter((n): n is string => n !== undefined)
      .map(Number),
  );
  const tokens = (diagnosis.prompt_tokens ?? 0) + (diagnosis.output_tokens ?? 0);

  return (
    <section
      aria-labelledby="report-title"
      className="space-y-5 rounded-lg border border-zinc-200 p-5 dark:border-zinc-800"
    >
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="report-title" className="text-lg font-semibold">
          {r.title}
        </h2>
        <VerificationBadge status={diagnosis.verification_status} />
      </div>

      {unknown && (
        <Alert tone="warning" title={r.unknownBanner}>
          {diagnosis.evidence_complete === false ? r.abstainedBody : r.unknownBody}
        </Alert>
      )}
      {diagnosis.verification_status === "conflicting" && (
        <Alert tone="warning" title={r.conflictingBanner}>
          {r.conflictingBody}
        </Alert>
      )}

      <Section title={r.causeStatus}>
        <p>{r.statusExplanation[diagnosis.verification_status]}</p>
      </Section>

      <dl className="grid gap-4 sm:grid-cols-3">
        <div>
          <dt className="text-xs uppercase tracking-wide text-muted">{r.category}</dt>
          <dd className="mt-1 font-medium">{categoryLabel(strings, diagnosis.category)}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-muted">{r.evidenceCheck}</dt>
          <dd className="mt-1">
            {diagnosis.citations.length > 0
              ? format(r.evidenceValid, {
                  valid: validCitations,
                  total: diagnosis.citations.length,
                })
              : r.evidenceNone}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-muted">{r.ruleHint}</dt>
          <dd className="mt-1">{categoryLabel(strings, diagnosis.rule_category)}</dd>
        </div>
      </dl>

      {!unknown && (
        <>
          <Section title={r.summary}>
            <p>{diagnosis.summary}</p>
          </Section>
          {diagnosis.root_cause && (
            <Section title={r.rootCause}>
              <p className="whitespace-pre-line">{diagnosis.root_cause}</p>
            </Section>
          )}
        </>
      )}

      {diagnosis.citations.length > 0 && (
        <Section title={r.citations}>
          <ul className="space-y-2">
            {diagnosis.citations.map((citation) => {
              const source = sources.get(citation.evidence_label);
              const inLog = source === undefined || source.source_type === "log";
              return (
                <li key={citation.ordinal} className="flex flex-wrap items-start gap-2">
                  <span className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-xs dark:bg-zinc-800">
                    {citation.evidence_label}
                  </span>
                  {citation.valid ? (
                    <button
                      type="button"
                      onClick={() => {
                        if (inLog) onShowLine(citation.line_number);
                        else onShowEvidence(citation.evidence_label);
                      }}
                      className="text-left font-mono text-xs text-sky-700 underline decoration-dotted underline-offset-2 hover:decoration-solid dark:text-sky-400"
                    >
                      {/* The visible text stays part of the accessible name (WCAG 2.5.3). */}
                      <span className="sr-only">
                        {inLog
                          ? format(r.showLine, { line: citation.line_number })
                          : format(r.showEvidence, { label: citation.evidence_label })}
                        :{" "}
                      </span>
                      {!inLog && `${source.document_name} `}L{citation.line_number}: “
                      {citation.quote}”
                    </button>
                  ) : (
                    <span className="font-mono text-xs text-muted line-through">
                      “{citation.quote}”
                      <span className="ml-2 no-underline">
                        ({r.citationRejected}: {citation.rejection_reason})
                      </span>
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </Section>
      )}

      <Section title={r.fixes}>
        <ol className="list-decimal space-y-1 pl-5">
          {diagnosis.recommended_fixes.map((fix, index) => (
            <li key={fix}>
              {fix}
              {flagged.has(index + 1) && (
                <span className="ml-2 rounded bg-amber-100 px-1 text-xs text-amber-900 dark:bg-amber-900 dark:text-amber-100">
                  {r.flagged}
                </span>
              )}
            </li>
          ))}
        </ol>
        <p className="mt-1 text-xs text-muted">{r.fixesNote}</p>
      </Section>

      {diagnosis.uncertainty && (
        <Section title={r.uncertainty}>
          <p>{diagnosis.uncertainty}</p>
        </Section>
      )}

      {diagnosis.verification_notes.length > 0 && (
        <Section title={r.notes}>
          <ul className="list-disc space-y-1 pl-5 text-zinc-600 dark:text-zinc-400">
            {diagnosis.verification_notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </Section>
      )}

      <p className="text-xs text-muted">
        {format(r.meta, {
          provider: diagnosis.model ?? strings.investigation.rulesOnly,
          tokens,
          seconds: ((diagnosis.duration_ms ?? 0) / 1000).toFixed(1),
        })}
        {diagnosis.diagnosis_attempts > 1 &&
          ` · ${format(r.attempts, { count: diagnosis.diagnosis_attempts })}`}
      </p>
    </section>
  );
}
