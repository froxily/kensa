import type { en } from "./en";

/** The shape of a locale: every key of `en`, with plain string values. */
type Widen<T> = { readonly [K in keyof T]: T[K] extends string ? string : Widen<T[K]> };

export type Messages = Widen<typeof en>;

export const LOCALES = ["en", "ja"] as const;
export type Locale = (typeof LOCALES)[number];
