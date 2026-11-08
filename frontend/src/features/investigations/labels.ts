import { label } from "../../i18n";
import type { Messages } from "../../i18n";

export function categoryLabel(strings: Messages, category: string | null): string {
  return category ? label(strings.categories, category) : "—";
}
