import { createContext, useContext } from "react";

import { en } from "./en";
import type { Locale, Messages } from "./messages";

export interface LocaleState {
  locale: Locale;
  strings: Messages;
  setLocale: (locale: Locale) => void;
}

// Without a provider (unit tests of single components) the UI is in English.
export const LocaleContext = createContext<LocaleState>({
  locale: "en",
  strings: en,
  setLocale: () => undefined,
});

export function useStrings(): Messages {
  return useContext(LocaleContext).strings;
}

export function useLocale(): Pick<LocaleState, "locale" | "setLocale"> {
  const { locale, setLocale } = useContext(LocaleContext);
  return { locale, setLocale };
}
