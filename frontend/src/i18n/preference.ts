import { CATALOG } from "./catalog";
import { LOCALES } from "./messages";
import type { Locale, Messages } from "./messages";

const STORAGE_KEY = "kensa.locale";

function isLocale(value: unknown): value is Locale {
  return LOCALES.some((locale) => locale === value);
}

// Storage can be unavailable (privacy mode, blocked site data); the UI must work without it.
export function readLocale(): Locale {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (isLocale(stored)) return stored;
  } catch {
    /* storage unavailable */
  }
  return navigator.language.toLowerCase().startsWith("ja") ? "ja" : "en";
}

export function saveLocale(locale: Locale): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    /* storage unavailable */
  }
}

// Code outside React (the replay adapter's messages) reads the active locale from here.
let active: Locale = "en";

export function applyLocale(locale: Locale): void {
  active = locale;
  document.documentElement.lang = locale;
}

export function currentMessages(): Messages {
  return CATALOG[active];
}
