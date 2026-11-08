import { useStrings } from "../../i18n";
import { useHealth } from "./useHealth";

type Tone = "neutral" | "ok" | "warn" | "error";

const dotClass: Record<Tone, string> = {
  neutral: "bg-zinc-400",
  ok: "bg-emerald-500",
  warn: "bg-amber-500",
  error: "bg-rose-500",
};

export function HealthIndicator() {
  const strings = useStrings();
  const { data, isPending, isError } = useHealth();

  let tone: Tone;
  let label: string;
  if (isPending) {
    tone = "neutral";
    label = strings.health.checking;
  } else if (isError) {
    tone = "error";
    label = strings.health.unreachable;
  } else if (data.status === "ok") {
    tone = "ok";
    label = strings.health.ready;
  } else {
    tone = "warn";
    label = strings.health.degraded;
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-2 whitespace-nowrap rounded-full border border-zinc-200 px-3 py-1 text-xs font-medium dark:border-zinc-800"
    >
      <span aria-hidden="true" className={`size-2 rounded-full ${dotClass[tone]}`} />
      <span>{label}</span>
    </div>
  );
}
