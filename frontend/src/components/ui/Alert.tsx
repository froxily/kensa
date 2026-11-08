import type { ReactNode } from "react";

import type { Tone } from "./Badge";

const tones: Record<Tone, string> = {
  neutral: "border-zinc-300 bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900",
  info: "border-sky-300 bg-sky-50 dark:border-sky-800 dark:bg-sky-950",
  success: "border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950",
  warning: "border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950",
  danger: "border-rose-300 bg-rose-50 dark:border-rose-800 dark:bg-rose-950",
};

export function Alert({
  tone = "neutral",
  title,
  children,
  urgent = false,
}: {
  tone?: Tone;
  title: string;
  children?: ReactNode;
  urgent?: boolean;
}) {
  return (
    <div role={urgent ? "alert" : "status"} className={`rounded-lg border p-4 ${tones[tone]}`}>
      <p className="text-sm font-semibold">{title}</p>
      {children && <div className="mt-1 text-sm text-zinc-700 dark:text-zinc-300">{children}</div>}
    </div>
  );
}
