import { useStrings } from "../../i18n";

/** Replaces the live service-health pill in the replay build, where nothing is running. */
export function ReplayStatus() {
  const strings = useStrings();
  return (
    <div className="flex items-center gap-2 whitespace-nowrap rounded-full border border-zinc-200 px-3 py-1 text-xs font-medium dark:border-zinc-800">
      <span aria-hidden="true" className="size-2 rounded-full bg-amber-500" />
      <span>{strings.replay.health}</span>
    </div>
  );
}
