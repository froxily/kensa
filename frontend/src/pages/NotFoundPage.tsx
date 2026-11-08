import { Link } from "react-router";

import { useStrings } from "../i18n";

export function NotFoundPage() {
  const strings = useStrings();
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">{strings.notFound.title}</h1>
      <Link to="/" className="text-sm text-sky-700 underline dark:text-sky-400">
        {strings.notFound.back}
      </Link>
    </div>
  );
}
