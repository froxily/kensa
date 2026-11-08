import { useEffect, useRef, useState } from "react";

import { buttonSecondary } from "../../../components/ui/button";
import { Spinner } from "../../../components/ui/Spinner";
import { format, useStrings } from "../../../i18n";
import { useDocument } from "../hooks";
import type { DocumentMeta } from "../types";

const MAX_RENDERED_LINES = 5_000;
const CONTEXT = 4;

interface Props {
  investigationId: string;
  document: DocumentMeta;
  /** Lines to emphasise (signatures and citations), 1-based. */
  marked: ReadonlySet<number>;
  /** The line a citation asked to show; scrolled into view and highlighted. */
  focusLine: number | null;
}

function visibleLines(total: number, marked: ReadonlySet<number>, showAll: boolean): number[] {
  if (showAll || marked.size === 0) {
    return Array.from({ length: Math.min(total, MAX_RENDERED_LINES) }, (_, i) => i + 1);
  }
  const keep = new Set<number>();
  for (const line of marked) {
    for (let n = line - CONTEXT; n <= line + CONTEXT; n += 1) {
      if (n >= 1 && n <= total) keep.add(n);
    }
  }
  return [...keep].sort((a, b) => a - b);
}

export function LogViewer({ investigationId, document, marked, focusLine }: Props) {
  const strings = useStrings();
  const { data, isPending, isError } = useDocument(investigationId, document.id);
  const [showAll, setShowAll] = useState(false);
  const focusRef = useRef<HTMLLIElement | null>(null);
  const needsAll = focusLine !== null && !marked.has(focusLine);

  useEffect(() => {
    focusRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [focusLine, data]);

  if (isPending) return <Spinner label={strings.common.loading} />;
  if (isError) return <p className="text-sm text-rose-600">{strings.common.unexpectedError}</p>;

  const lines = visibleLines(data.lines.length, marked, showAll || needsAll);
  return (
    <section aria-labelledby="log-title" className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 id="log-title" className="text-base font-semibold">
            {strings.log.title}: <span className="font-mono text-sm">{document.name}</span>
          </h2>
          {document.redaction_count > 0 && (
            <p className="text-xs text-muted">
              {format(strings.log.redactions, { count: document.redaction_count })}
            </p>
          )}
        </div>
        <button
          type="button"
          className={buttonSecondary}
          onClick={() => {
            setShowAll((value) => !value);
          }}
        >
          {showAll ? strings.log.showErrors : strings.log.showAll}
        </button>
      </div>
      <div
        role="region"
        aria-label={strings.log.region}
        tabIndex={0}
        className="max-h-[32rem] overflow-auto rounded-lg border border-zinc-200 bg-zinc-50 font-mono text-xs dark:border-zinc-800 dark:bg-zinc-900"
      >
        <ol className="min-w-max py-2">
          {lines.map((number, index) => {
            const gap = index > 0 && number !== (lines[index - 1] ?? 0) + 1;
            const isFocus = number === focusLine;
            const isMarked = marked.has(number);
            return (
              <li
                key={number}
                ref={isFocus ? focusRef : undefined}
                data-line={number}
                aria-current={isFocus ? "location" : undefined}
                className={`flex gap-4 px-3 ${gap ? "mt-2 border-t border-dashed border-zinc-300 pt-2 dark:border-zinc-700" : ""} ${
                  isFocus
                    ? "bg-sky-100 dark:bg-sky-900/60"
                    : isMarked
                      ? "bg-amber-50 dark:bg-amber-950/50"
                      : ""
                }`}
              >
                <span className="w-12 shrink-0 select-none text-right text-muted">{number}</span>
                <span className="whitespace-pre">{data.lines[number - 1]}</span>
              </li>
            );
          })}
        </ol>
      </div>
      {data.lines.length > MAX_RENDERED_LINES && (showAll || needsAll) && (
        <p className="text-xs text-muted">
          {format(strings.log.tooLong, { count: MAX_RENDERED_LINES })}
        </p>
      )}
    </section>
  );
}
