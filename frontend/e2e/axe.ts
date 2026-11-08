import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

import { en } from "../src/i18n/en";
import { ja } from "../src/i18n/ja";
import type { Locale, Messages } from "../src/i18n/messages";

export const CATALOGS: Record<Locale, Messages> = { en, ja };

/** Starts the page in a language, as a returning user who chose it would see it. */
export async function useLocale(page: Page, locale: Locale): Promise<void> {
  // A script string: this file is compiled without the browser's DOM types.
  await page.addInitScript({
    content: `window.localStorage.setItem("kensa.locale", ${JSON.stringify(locale)});`,
  });
}

export async function expectNoSeriousViolations(page: Page, label: string): Promise<void> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const serious = results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => {
      const nodes = v.nodes.map((n) => {
        const data = n.any[0]?.data as
          { contrastRatio?: number; fgColor?: string; bgColor?: string } | undefined;
        const contrast = data?.contrastRatio
          ? ` [${String(data.contrastRatio)}:1 ${data.fgColor ?? ""} on ${data.bgColor ?? ""}]`
          : "";
        return `${n.target.join(" ")}${contrast}`;
      });
      return `${v.id}: ${nodes.join(" | ")}`;
    });
  expect(serious, `${label}: serious or critical axe violations`).toEqual([]);
}
