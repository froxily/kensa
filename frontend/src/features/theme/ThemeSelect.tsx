import { useEffect, useId, useState } from "react";

import { useStrings } from "../../i18n";
import {
  THEME_PREFERENCES,
  applyTheme,
  readPreference,
  savePreference,
  watchSystemTheme,
  type ThemePreference,
} from "./theme";

export function ThemeSelect() {
  const strings = useStrings();
  const id = useId();
  const [preference, setPreference] = useState<ThemePreference>(readPreference);

  useEffect(() => {
    applyTheme(preference);
    if (preference !== "system") return undefined;
    return watchSystemTheme(() => {
      applyTheme("system");
    });
  }, [preference]);

  return (
    <div className="flex items-center gap-2 text-sm">
      <label htmlFor={id} className="sr-only">
        {strings.theme.label}
      </label>
      <select
        id={id}
        value={preference}
        onChange={(event) => {
          const next = event.target.value as ThemePreference;
          savePreference(next);
          setPreference(next);
        }}
        className="rounded-md border border-zinc-300 bg-transparent px-2 py-1 dark:border-zinc-700"
      >
        {THEME_PREFERENCES.map((option) => (
          <option key={option} value={option}>
            {strings.theme[option]}
          </option>
        ))}
      </select>
    </div>
  );
}
