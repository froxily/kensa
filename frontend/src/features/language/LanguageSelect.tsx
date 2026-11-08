import { useId } from "react";

import { LOCALES, useLocale, useStrings } from "../../i18n";
import type { Locale } from "../../i18n";

export function LanguageSelect() {
  const id = useId();
  const strings = useStrings();
  const { locale, setLocale } = useLocale();

  return (
    <div className="flex items-center gap-2 text-sm">
      <label htmlFor={id} className="sr-only">
        {strings.language.label}
      </label>
      <select
        id={id}
        value={locale}
        onChange={(event) => {
          setLocale(event.target.value as Locale);
        }}
        className="rounded-md border border-zinc-300 bg-transparent px-2 py-1 dark:border-zinc-700"
      >
        {LOCALES.map((option) => (
          // Each language is named in itself, and marked so screen readers pronounce it correctly.
          <option key={option} value={option} lang={option}>
            {strings.language[option]}
          </option>
        ))}
      </select>
    </div>
  );
}
