import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { CATALOG } from "./catalog";
import { LocaleContext } from "./context";
import type { Locale } from "./messages";
import { applyLocale, readLocale, saveLocale } from "./preference";

export function LocaleProvider({ children, initial }: { children: ReactNode; initial?: Locale }) {
  const [locale, setLocaleState] = useState<Locale>(() => initial ?? readLocale());

  useEffect(() => {
    applyLocale(locale);
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    saveLocale(next);
    setLocaleState(next);
  }, []);

  const value = useMemo(
    () => ({ locale, strings: CATALOG[locale], setLocale }),
    [locale, setLocale],
  );
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}
