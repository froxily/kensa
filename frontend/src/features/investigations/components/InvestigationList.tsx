import { Link } from "react-router";

import { useLocale, useStrings } from "../../../i18n";
import { formatDateTime } from "../../../lib/format";
import type { InvestigationSummary } from "../types";
import { categoryLabel } from "../labels";
import { StatusBadge, VerificationBadge } from "./Badges";

export function InvestigationList({ items }: { items: InvestigationSummary[] }) {
  const strings = useStrings();
  const { locale } = useLocale();
  const columns = strings.overview.columns;
  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">{strings.overview.recent}</caption>
        <thead className="bg-zinc-50 text-xs uppercase tracking-wide text-muted dark:bg-zinc-900">
          <tr>
            <th scope="col" className="px-4 py-2 font-medium">
              {columns.title}
            </th>
            <th scope="col" className="px-4 py-2 font-medium">
              {columns.status}
            </th>
            <th scope="col" className="px-4 py-2 font-medium">
              {columns.category}
            </th>
            <th scope="col" className="hidden px-4 py-2 font-medium sm:table-cell">
              {columns.created}
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
          {items.map((item) => (
            <tr key={item.id} className="hover:bg-zinc-50 dark:hover:bg-zinc-900/60">
              <td className="max-w-md px-4 py-3">
                <Link
                  to={`/investigations/${item.id}`}
                  className="line-clamp-2 font-medium text-sky-700 hover:underline dark:text-sky-400"
                >
                  {item.title}
                </Link>
              </td>
              <td className="px-4 py-3">
                <StatusBadge status={item.status} />
              </td>
              <td className="px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span>{categoryLabel(strings, item.category)}</span>
                  {item.verification_status && (
                    <VerificationBadge status={item.verification_status} />
                  )}
                </div>
              </td>
              <td className="hidden whitespace-nowrap px-4 py-3 text-muted sm:table-cell">
                {formatDateTime(item.created_at, locale)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
