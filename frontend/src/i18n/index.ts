export { LocaleProvider } from "./LocaleProvider";
export { useLocale, useStrings } from "./context";
export { currentMessages } from "./preference";
export { LOCALES } from "./messages";
export type { Locale, Messages } from "./messages";

/** Fills `{name}` placeholders in a message. */
export function format(message: string, values: Record<string, string | number>): string {
  return message.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in values ? String(values[key]) : match,
  );
}

/** Looks up a label for a backend value, falling back to the raw value. */
export function label(table: Readonly<Record<string, string>>, key: string): string {
  return table[key] ?? key;
}
