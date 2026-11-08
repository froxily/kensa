import { readFileSync } from "node:fs";

import { expect, test, type Locator, type Page } from "@playwright/test";

import { CATALOGS, expectNoSeriousViolations, useLocale } from "./axe";

// The static replay build (npm run build:replay), served by `vite preview` with no proxy, or a
// deployed copy of it (KENSA_REPLAY_URL, e.g. the GitHub Pages demo). Pages are addressed
// relative to it ("./#/..."), so the same tests work under a sub-path.
const REPLAY = (process.env.KENSA_REPLAY_URL ?? "http://127.0.0.1:4174").replace(/\/?$/, "/");

interface RecordedInvestigation {
  id: string;
  title: string;
  status: string;
  category: string | null;
  verification_status: string | null;
}

const recording = JSON.parse(
  readFileSync(new URL("../replay/recording.json", import.meta.url), "utf-8"),
) as { manifest: { model: string }; investigations: RecordedInvestigation[] };

function recorded(predicate: (item: RecordedInvestigation) => boolean): RecordedInvestigation {
  const found = recording.investigations.find(predicate);
  if (!found) throw new Error("the recording lacks a run this test needs");
  return found;
}

const awaitingApproval = recorded((item) => item.status === "awaiting_approval");
const abstained = recorded((item) => item.verification_status === "not_established");

/** Collects every request the page makes, to prove the replay never leaves its own files. */
function watchRequests(page: Page): string[] {
  const urls: string[] = [];
  page.on("request", (request) => urls.push(request.url()));
  return urls;
}

function offLimits(urls: string[]): string[] {
  return urls.filter((url) => !url.startsWith(REPLAY) || url.includes("/api/"));
}

/** Aborts every request except the replay's own files and returns what was blocked. */
async function blockAllButReplay(page: Page): Promise<string[]> {
  const blocked: string[] = [];
  await page.route("**/*", (route) => {
    const url = route.request().url();
    if (offLimits([url]).length === 0) return route.continue();
    blocked.push(url);
    return route.abort("blockedbyclient");
  });
  return blocked;
}

/** Collects uncaught page errors and console errors. */
function watchErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  return errors;
}

/** Presses Tab until the element has focus, as a keyboard user would reach it. */
async function tabTo(page: Page, target: Locator, limit = 60) {
  for (let presses = 0; presses < limit; presses += 1) {
    try {
      await expect(target).toBeFocused({ timeout: 50 });
      return;
    } catch {
      await page.keyboard.press("Tab");
    }
  }
  throw new Error(`not reachable with ${String(limit)} presses of Tab`);
}

async function focusOutline(page: Page): Promise<string> {
  return page.evaluate<string>("getComputedStyle(document.activeElement).outlineStyle");
}

const PAGES = [
  "./",
  "./#/investigations/new",
  ...recording.investigations.map((item) => `./#/investigations/${item.id}`),
];

test.use({ baseURL: REPLAY });

test("the replay shows recorded runs, labelled as a replay, and never calls an API", async ({
  page,
}) => {
  const requests = watchRequests(page);
  const strings = CATALOGS.en;
  await page.goto("./");
  const banner = page.getByRole("note");
  await expect(banner).toContainText("Prerecorded interactive replay, not live AI inference");
  await expect(banner).toContainText(recording.manifest.model);
  await expect(page.getByText(strings.replay.health)).toBeVisible();
  await expect(page.getByRole("heading", { name: strings.health.panelTitle })).toHaveCount(0);
  // The bundled packages' licences ship with the build, linked from every page.
  const notices = await banner
    .getByRole("link", { name: strings.replay.notices })
    .getAttribute("href");
  const response = await page.request.get(new URL(notices ?? "", REPLAY).href);
  expect(response.status()).toBe(200);
  const text = await response.text();
  for (const expected of ["MIT License", "react-dom", "@tanstack/react-query", "react-router"]) {
    expect(text).toContain(expected);
  }
  for (const item of recording.investigations) {
    await expect(page.getByRole("link", { name: item.title })).toBeVisible();
  }

  await page
    .getByRole("navigation", { name: strings.nav.label })
    .getByRole("link", { name: strings.nav.newInvestigation })
    .click();
  await expect(page.getByText(strings.replay.createDisabled)).toBeVisible();
  await expect(page.getByRole("button", { name: strings.create.submit })).toBeDisabled();

  await page.goto(`./#/investigations/${abstained.id}`);
  await expect(page.getByRole("heading", { level: 1, name: abstained.title })).toBeVisible();
  await expect(
    page.getByRole("main").getByText(strings.replay.badge, { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(strings.report.unknownBanner, { exact: true })).toBeVisible();
  expect(offLimits(requests)).toEqual([]);
});

test("a decision in the replay is labelled temporary and kept in the tab only", async ({
  page,
}) => {
  const strings = CATALOGS.en;
  await page.goto(`./#/investigations/${awaitingApproval.id}`);
  await expect(page.getByRole("region", { name: strings.review.title })).toBeVisible();
  const approve = page.getByRole("button", { name: strings.review.approve });
  await expect(page.getByText(strings.replay.decisionTemporary)).toBeVisible();
  await expect(approve).toHaveAccessibleDescription(strings.replay.decisionTemporary);
  await expect(
    page.getByRole("button", { name: strings.review.reject }),
  ).toHaveAccessibleDescription(strings.replay.decisionTemporary);
  await approve.click();
  await expect(page.getByText(strings.replay.decisionNotSaved)).toBeVisible();
  await expect(page.getByText(strings.review.notApplied)).toBeVisible();

  await page.reload();
  await expect(page.getByRole("button", { name: strings.review.approve })).toBeVisible();
  await expect(page.getByText(strings.replay.decisionNotSaved)).toHaveCount(0);
});

test("the replay works with every request outside its own files blocked", async ({ page }) => {
  const blocked = await blockAllButReplay(page);
  const errors = watchErrors(page);
  const strings = CATALOGS.en;
  await page.goto("./");
  await expect(page.getByRole("note")).toContainText(recording.manifest.model);
  for (const item of recording.investigations) {
    await page.goto("./");
    await page.getByRole("link", { name: item.title }).click();
    await expect(page.getByRole("heading", { level: 1, name: item.title })).toBeVisible();
    await expect(page.getByRole("region", { name: strings.report.title })).toBeVisible();
    await expect(page.getByRole("region", { name: strings.log.region })).toBeVisible();
  }
  await page.goto(`./#/investigations/${awaitingApproval.id}`);
  await page.getByRole("button", { name: strings.review.approve }).click();
  await expect(page.getByText(strings.replay.decisionNotSaved)).toBeVisible();
  await page.goto("./#/investigations/new");
  await expect(page.getByText(strings.replay.createDisabled)).toBeVisible();
  await page.getByLabel(strings.language.label, { exact: true }).selectOption("ja");
  await expect(
    page.getByRole("heading", { level: 1, name: CATALOGS.ja.create.title }),
  ).toBeVisible();
  expect(blocked).toEqual([]);
  expect(errors).toEqual([]);
});

test("the replay works with the keyboard alone", async ({ page }) => {
  const strings = CATALOGS.en;
  await page.goto("./");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  // The first Tab shows the skip link; the header's controls follow it.
  const skip = page.getByRole("link", { name: strings.app.skipToContent });
  await page.keyboard.press("Tab");
  await expect(skip).toBeFocused();
  await expect(skip).toBeInViewport();
  const language = page.getByLabel(strings.language.label, { exact: true });
  await tabTo(page, language);
  expect(await focusOutline(page)).not.toBe("none");
  await page.keyboard.press("ArrowDown");
  await expect(page.locator("html")).toHaveAttribute("lang", "ja");
  await expect(
    page.getByRole("heading", { level: 1, name: CATALOGS.ja.overview.title }),
  ).toBeVisible();
  await page.keyboard.press("ArrowUp");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");

  // The skip link moves focus past the header, to the page's content.
  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(skip).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("main")).toBeFocused();
  await tabTo(page, page.getByRole("link", { name: awaitingApproval.title }));
  expect(await focusOutline(page)).not.toBe("none");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 1, name: awaitingApproval.title })).toBeVisible();

  const citation = page
    .getByRole("region", { name: strings.report.title })
    .getByRole("button", { name: new RegExp(`^${strings.report.showLine.split("{line}")[0]}`) })
    .first();
  await tabTo(page, citation);
  expect(await focusOutline(page)).not.toBe("none");
  await page.keyboard.press("Enter");
  await expect(page.locator('li[aria-current="location"]')).toBeInViewport();

  const approve = page.getByRole("button", { name: strings.review.approve });
  await tabTo(page, approve);
  expect(await focusOutline(page)).not.toBe("none");
  await page.keyboard.press("Enter");
  await expect(page.getByText(strings.replay.decisionNotSaved)).toBeVisible();
});

for (const locale of ["en", "ja"] as const) {
  test(`every replay page fits a phone screen without sideways scrolling (${locale})`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await useLocale(page, locale);
    for (const path of PAGES) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      const overflow = await page.evaluate<number>(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth",
      );
      expect(overflow, `${path} scrolls sideways by ${String(overflow)} px`).toBeLessThanOrEqual(0);
    }
    await page.goto(`./#/investigations/${awaitingApproval.id}`);
    await expect(page.getByRole("region", { name: CATALOGS[locale].review.title })).toBeVisible();
    await expectNoSeriousViolations(page, `replay on a phone (${locale})`);
  });
}

for (const [scheme, locale] of [
  ["light", "en"],
  ["dark", "en"],
  ["light", "ja"],
  ["dark", "ja"],
] as const) {
  test(`replay pages have no serious accessibility violations (${scheme}, ${locale})`, async ({
    page,
  }) => {
    const requests = watchRequests(page);
    const strings = CATALOGS[locale];
    await useLocale(page, locale);
    await page.emulateMedia({ colorScheme: scheme });
    for (const [label, path] of [
      ["overview", "./"],
      ["new investigation", "./#/investigations/new"],
      ["awaiting approval", `./#/investigations/${awaitingApproval.id}`],
      ["abstention", `./#/investigations/${abstained.id}`],
    ] as const) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await expect(page.getByRole("note")).toContainText(recording.manifest.model);
      await expect(page.locator("html")).toHaveAttribute("lang", locale);
      if (label === "awaiting approval") {
        await expect(page.getByRole("region", { name: strings.review.title })).toBeVisible();
      }
      await expectNoSeriousViolations(page, `replay ${label} (${scheme}, ${locale})`);
    }
    expect(offLimits(requests)).toEqual([]);
  });
}
