import { label, useStrings } from "../../../i18n";
import type { AgentEvent } from "../types";

const dot: Record<AgentEvent["event_type"], string> = {
  started: "bg-sky-500",
  completed: "bg-emerald-500",
  failed: "bg-rose-500",
  info: "bg-amber-500",
};

export function Timeline({ events }: { events: AgentEvent[] }) {
  const strings = useStrings();
  return (
    <section aria-labelledby="timeline-title" className="space-y-3">
      <h2 id="timeline-title" className="text-base font-semibold">
        {strings.investigation.timeline}
      </h2>
      {events.length === 0 ? (
        <p className="text-sm text-muted">{strings.investigation.timelineEmpty}</p>
      ) : (
        <ol
          aria-live="polite"
          className="space-y-2 border-l border-zinc-200 pl-4 dark:border-zinc-800"
        >
          {events.map((event) => (
            <li key={event.seq} className="relative">
              <span
                aria-hidden="true"
                className={`absolute -left-[1.3rem] top-1.5 size-2 rounded-full ${dot[event.event_type]}`}
              />
              <p className="text-sm">
                <span className="font-medium">{label(strings.nodes, event.node)}</span>
                <span className="sr-only"> ({event.event_type})</span>
                <span className="text-muted">
                  {" "}
                  · {strings.investigation.attempt} {event.attempt}
                  {event.duration_ms !== null && ` · ${String(event.duration_ms)} ms`}
                </span>
              </p>
              <p className="text-sm text-zinc-600 dark:text-zinc-400">{event.summary}</p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
