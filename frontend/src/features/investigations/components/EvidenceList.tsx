import { format, label, useStrings } from "../../../i18n";
import { evidenceElementId } from "../evidence";
import type { EvidenceItem } from "../types";

export function EvidenceList({
  evidence,
  onShowLine,
}: {
  evidence: EvidenceItem[];
  onShowLine: (line: number) => void;
}) {
  const strings = useStrings();
  if (evidence.length === 0) return null;
  return (
    <section aria-labelledby="evidence-title" className="space-y-3">
      <h2 id="evidence-title" className="text-base font-semibold">
        {strings.evidence.title}
      </h2>
      <ul className="space-y-3">
        {evidence.map((item) => (
          <li
            key={item.label}
            id={evidenceElementId(item.label)}
            tabIndex={-1}
            className="rounded-lg border border-zinc-200 outline-none focus:ring-2 focus:ring-sky-600 dark:border-zinc-800"
          >
            <div className="flex flex-wrap items-center gap-2 border-b border-zinc-200 px-3 py-2 text-xs dark:border-zinc-800">
              <span className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono dark:bg-zinc-800">
                {item.label}
              </span>
              {item.source_type === "log" ? (
                <button
                  type="button"
                  className="font-mono text-sky-700 hover:underline dark:text-sky-400"
                  onClick={() => {
                    onShowLine(item.start_line);
                  }}
                >
                  L{item.start_line}–{item.end_line}
                </button>
              ) : (
                <>
                  <span className="rounded border border-zinc-300 px-1.5 py-0.5 dark:border-zinc-700">
                    {label(strings.evidence.source, item.source_type)}
                  </span>
                  <span className="font-mono [overflow-wrap:anywhere]">{item.document_name}</span>
                  <span className="font-mono text-muted">
                    L{item.start_line}–{item.end_line}
                  </span>
                </>
              )}
              {item.commit_sha && item.source_url && (
                <>
                  <span className="text-muted">
                    {format(strings.evidence.commit, { sha: item.commit_sha.slice(0, 7) })}
                  </span>
                  <a
                    href={item.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sky-700 underline dark:text-sky-400"
                  >
                    {strings.evidence.viewOnGitHub}{" "}
                    <span className="sr-only">{strings.common.opensNewTab}</span>
                  </a>
                </>
              )}
              {item.step_name && <span className="text-muted">{item.step_name}</span>}
              <span className="ml-auto text-muted">
                {strings.evidence.channels}:{" "}
                {item.channels.map((c) => label(strings.evidence.channel, c)).join(", ")}
              </span>
            </div>
            {/* Wrapped rather than horizontally scrollable: no keyboard-trapped scroll region. */}
            <pre className="whitespace-pre-wrap px-3 py-2 font-mono text-xs leading-5 [overflow-wrap:anywhere]">
              {item.lines
                .map((line, i) => `${String(item.start_line + i).padStart(4)}  ${line}`)
                .join("\n")}
            </pre>
          </li>
        ))}
      </ul>
    </section>
  );
}
