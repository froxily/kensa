import type { Locale } from "../i18n";

const dateTimes: Record<Locale, Intl.DateTimeFormat> = {
  en: new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }),
  ja: new Intl.DateTimeFormat("ja-JP", { dateStyle: "medium", timeStyle: "short" }),
};

/** Formats a timestamp in the UI's language (not the browser's), so the page reads consistently. */
export function formatDateTime(iso: string, locale: Locale): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : dateTimes[locale].format(date);
}

export function formatPercent(value: number): string {
  return `${String(Math.round(value * 100))}%`;
}

export function formatNumber(value: number, locale: Locale): string {
  return new Intl.NumberFormat(locale === "ja" ? "ja-JP" : "en").format(value);
}
