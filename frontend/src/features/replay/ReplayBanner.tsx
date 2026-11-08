import { useQuery } from "@tanstack/react-query";

import { format, useLocale, useStrings } from "../../i18n";
import { formatDateTime } from "../../lib/format";

// Shown on every page of the replay build, so a recorded run is never mistaken for a live one.
export function ReplayBanner() {
  const strings = useStrings();
  const { locale } = useLocale();
  const manifest = useQuery({
    queryKey: ["replay", "manifest"],
    queryFn: () => import("../../lib/api/replay").then((replay) => replay.replayManifest()),
    staleTime: Infinity,
  });

  return (
    <div
      role="note"
      className="border-b border-amber-300 bg-amber-50 text-amber-950 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100"
    >
      <p className="mx-auto max-w-6xl px-4 py-2 text-sm">
        <span className="mr-2 rounded bg-amber-200 px-1.5 py-0.5 text-xs font-semibold uppercase tracking-wide dark:bg-amber-800">
          {strings.replay.badge}
        </span>
        {manifest.data
          ? format(strings.replay.banner, {
              date: formatDateTime(manifest.data.recorded_at, locale),
              model: manifest.data.model,
            })
          : strings.replay.health}{" "}
        {/* Shipped next to index.html: the bundled packages' licences travel with the build. */}
        <a
          href={`${import.meta.env.BASE_URL}THIRD_PARTY_NOTICES.txt`}
          className="whitespace-nowrap underline"
        >
          {strings.replay.notices}
        </a>
      </p>
    </div>
  );
}
