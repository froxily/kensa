import { en } from "./en";
import { ja } from "./ja";
import type { Locale, Messages } from "./messages";

export const CATALOG: Readonly<Record<Locale, Messages>> = { en, ja };
