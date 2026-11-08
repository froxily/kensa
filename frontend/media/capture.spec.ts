import { execFileSync } from "node:child_process";
import { readFileSync, readdirSync } from "node:fs";
import { mkdir, mkdtemp, readdir, rename, rm, stat, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

import { CATALOGS, useLocale as setLocale } from "../e2e/axe";

interface Investigation {
  id: string;
  title: string;
  status: string;
  category: string | null;
  verification_status: string | null;
  diagnosis: { citations: { valid: boolean; evidence_label: string }[] } | null;
  evidence: { label: string; source_type: string }[];
  proposals: { risks: string[] }[];
}
const recording = JSON.parse(
  readFileSync(new URL("../replay/recording.json", import.meta.url), "utf8"),
) as { manifest: { model: string }; investigations: Investigation[] };
function recorded(predicate: (item: Investigation) => boolean): Investigation {
  const item = recording.investigations.find(predicate);
  if (!item) throw new Error("Required investigation missing from recording");
  return item;
}
const sample = recorded(
  (item) => item.verification_status === "corroborated" && item.status === "awaiting_approval",
);
const regression = recorded((item) => item.category === "test_regression");
const abstention = recorded((item) => item.verification_status === "not_established");
const output = fileURLToPath(new URL("../../docs/media/", import.meta.url));
const pathFor = (item: Investigation) => `/#/investigations/${item.id}`;

/** Waits until the page has finished loading what a screenshot or the video shows. */
async function ready(page: Page, locale: "en" | "ja", investigation = false) {
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("note")).toContainText(recording.manifest.model);
  await expect(page.getByText(CATALOGS[locale].common.loading)).toHaveCount(0);
  if (investigation) {
    await expect(page.getByRole("region", { name: CATALOGS[locale].report.title })).toBeVisible();
    await expect(page.getByRole("region", { name: CATALOGS[locale].log.region })).toBeVisible();
  } else if (new URL(page.url()).hash === "#/" || new URL(page.url()).hash === "") {
    await expect(page.getByRole("link", { name: sample.title })).toBeVisible();
  }
}
/** Scrolls the page so the region starts near the top of the viewport. */
async function top(page: Page, name: string) {
  // A string passed to evaluate() is run as an expression, so "element => ..." would never be
  // called; the scroll is computed from the region's box instead.
  const box = await page.getByRole("region", { name }).boundingBox();
  if (!box) throw new Error(`The region "${name}" is not on the page`);
  await page.evaluate(`window.scrollBy(0, ${String(Math.round(box.y - 16))})`);
  await expect
    .poll(async () => (await page.getByRole("region", { name }).boundingBox())?.y)
    .toBeLessThan(40);
}

// The video's captions, in English (shown in the picture) and Japanese (in the caption file and
// the transcript). Counts, titles and status names come from the recording and the UI's own
// labels. The two sentences about the test regression's proposals were checked by hand against
// the recording of 2 November 2026; the assertions below fail if a new recording changes them.
const en = CATALOGS.en;
const ja = CATALOGS.ja;
const model = recording.manifest.model.split("-")[0] ?? recording.manifest.model;
const runs = String(recording.investigations.length);
const cited = sample.diagnosis?.citations ?? [];
const citationsFound = String(cited.filter((citation) => citation.valid).length);
const citationCount = String(cited.length);
// Where the sample's citations point: not every cited line is in the job log.
const SOURCES: Partial<Record<string, { en: string; ja: string }>> = {
  log: { en: "in the job log", ja: "ジョブログ" },
  kb: { en: "in knowledge-base notes", ja: "ナレッジベース" },
  code: { en: "in repository code", ja: "リポジトリのコード" },
  workflow_yaml: { en: "in the workflow file", ja: "ワークフローファイル" },
};
const sourceCounts = new Map<string, number>();
for (const citation of cited) {
  const item = sample.evidence.find((evidence) => evidence.label === citation.evidence_label);
  const kind = item?.source_type ?? "unknown";
  sourceCounts.set(kind, (sourceCounts.get(kind) ?? 0) + 1);
}
const sourceList = (locale: "en" | "ja") =>
  [...sourceCounts]
    .map(([kind, count]) => {
      const where = SOURCES[kind];
      if (!where) throw new Error(`No caption wording for citations from ${kind}`);
      return locale === "en" ? `${String(count)} ${where.en}` : `${where.ja} ${String(count)} 件`;
    })
    .join(locale === "en" ? ", " : "、");
const TEST_RISK = "Changing the test instead of the code hides a real regression";
const CAPTIONS = {
  intro: {
    en: `A replay of ${runs} real Kensa runs, recorded with a local model (${model}) on a 4 GB laptop GPU. Nothing is running now.`,
    ja: `4 GB のノート PC 向け GPU 上のローカルモデル（${model}）で記録した、Kensa の実際の実行 ${runs} 件のリプレイです。現在は何も実行されていません。`,
  },
  sample: {
    en: `A built-in sample: "${sample.title}".`,
    ja: `組み込みサンプル：「${sample.title}」`,
  },
  report: {
    en: `Every claim cites a source line. The verifier found ${citationsFound} of ${citationCount} quotes on their cited lines (${sourceList("en")}), and the log itself states the cause: "${en.verification.corroborated}".`,
    ja: `すべての主張は根拠となる行を引用します。検証器は ${citationCount} 件中 ${citationsFound} 件の引用を引用先の行で確認しました（${sourceList("ja")}）。ログ自体に原因が記載されているため「${ja.verification.corroborated}」です。`,
  },
  citation: {
    en: "A citation of the log opens its line in the stored log; other citations open their evidence excerpt.",
    ja: "ログの引用は保存されたログの該当行を開き、それ以外の引用は該当する証拠の抜粋を開きます。",
  },
  review: {
    en: "Fixes are proposals only. Kensa never changes a repository.",
    ja: "修正は提案のみです。Kensa がリポジトリを変更することはありません。",
  },
  decision: {
    en: "In the replay, a decision is kept in this browser tab only. Nothing is saved.",
    ja: "リプレイでは、判断はこのブラウザーのタブ内でのみ保持され、保存されません。",
  },
  regression: {
    en: `A failing test is a symptom, so a test regression is at most "${en.verification.plausible}".`,
    ja: `失敗したテストは症状にすぎないため、テストのリグレッションは最大でも「${ja.verification.plausible}」です。`,
  },
  regressionReview: {
    en: `The model's proposals are shown as produced, mistakes included: 2 of the ${String(regression.proposals.length)} would change the test instead of the code. Each carries the risk that this hides a real regression.`,
    ja: `モデルの提案は誤りも含めて生成されたまま表示されます。${String(regression.proposals.length)} 件中 2 件はコードではなくテストを変更する提案です。どの提案にも、それが本当のリグレッションを隠しうるというリスクが示されています。`,
  },
  abstention: {
    en: `This log does not show the failure, so Kensa does not ask the model to guess: "${en.verification.not_established}".`,
    ja: `このログには失敗が示されていないため、Kensa はモデルに推測させません（「${ja.verification.not_established}」）。`,
  },
  japanese: {
    en: "The interface is also in Japanese. Recorded model output stays in English.",
    ja: "UI は日本語にも対応しています。記録されたモデルの出力は英語のままです。",
  },
};

interface Cue {
  start: number;
  end: number;
  en: string;
  ja: string;
}

function timestamp(seconds: number): string {
  const whole = Math.floor(seconds);
  const parts = [Math.floor(whole / 3600), Math.floor(whole / 60) % 60, whole % 60];
  const millis = String(Math.round((seconds - whole) * 1000)).padStart(3, "0");
  return `${parts.map((part) => String(part).padStart(2, "0")).join(":")}.${millis}`;
}

function webVtt(cues: Cue[], locale: "en" | "ja"): string {
  const blocks = cues.map(
    (cue, index) =>
      `${String(index + 1)}\n${timestamp(cue.start)} --> ${timestamp(cue.end)}\n${cue[locale]}`,
  );
  return `WEBVTT\n\n${blocks.join("\n\n")}\n`;
}

function transcript(cues: Cue[], seconds: number): string {
  const rows = cues.map((cue) =>
    `| ${timestamp(cue.start).slice(3, 8)} | ${cue.en} | ${cue.ja} |`.replaceAll("\n", " "),
  );
  return [
    "# Demo video: transcript",
    "",
    `[kensa-demo.webm](kensa-demo.webm) is about ${String(Math.round(seconds))} seconds long and has no sound. It was captured by \`npm --prefix frontend run media\` from the replay build, which shows ${runs} runs recorded with the local model. The English captions are part of the picture. The same captions, with timings, are in [kensa-demo.en.vtt](kensa-demo.en.vtt) and, in Japanese, [kensa-demo.ja.vtt](kensa-demo.ja.vtt).`,
    "",
    "動画には音声がありません。英語の字幕は映像に含まれています。日本語の字幕は kensa-demo.ja.vtt と下の表にあります。",
    "",
    "| Time | Caption | 字幕 |",
    "|---|---|---|",
    ...rows,
    "",
  ].join("\n");
}

test("capture screenshots and demo", async ({ browser }) => {
  expect(regression.proposals).toHaveLength(5);
  for (const proposal of regression.proposals) {
    expect(proposal.risks.some((risk) => risk.startsWith(TEST_RISK))).toBe(true);
  }
  await mkdir(output, { recursive: true });
  for (const [locale, scheme, suffix] of [
    ["en", "light", "en"],
    ["ja", "light", "ja"],
    ["en", "dark", "dark-en"],
  ] as const) {
    const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    await context.route("**/*", (route) =>
      route.request().url().startsWith("http://127.0.0.1:4174/") ? route.continue() : route.abort(),
    );
    const page = await context.newPage();
    await setLocale(page, locale);
    await page.emulateMedia({ colorScheme: scheme });
    await page.goto("/");
    await ready(page, locale);
    await page.screenshot({ path: join(output, `overview-${suffix}.png`), animations: "disabled" });
    await page.goto(pathFor(sample));
    await ready(page, locale, true);
    await top(page, CATALOGS[locale].report.title);
    await page.screenshot({ path: join(output, `report-${suffix}.png`), animations: "disabled" });
    if (locale === "en" && scheme === "light") {
      await page.goto(pathFor(regression));
      await ready(page, locale, true);
      await page.getByRole("region", { name: CATALOGS.en.review.title }).screenshot({
        path: join(output, "diff-review-en.png"),
        animations: "disabled",
      });
      await page.goto(pathFor(abstention));
      await ready(page, locale, true);
      await top(page, CATALOGS.en.report.title);
      await page.screenshot({ path: join(output, "abstention-en.png"), animations: "disabled" });
      await page.goto("/#/investigations/new");
      await ready(page, locale);
      await expect(page.getByText(CATALOGS.en.replay.createDisabled)).toBeVisible();
      // A hash route keeps the previous page's scroll position.
      await page.evaluate("window.scrollTo(0, 0)");
      await page.screenshot({
        path: join(output, "new-investigation-en.png"),
        animations: "disabled",
      });
    }
    await context.close();
  }

  // A phone-sized view (375 x 812 CSS pixels), in Japanese.
  const phone = await browser.newContext({
    viewport: { width: 375, height: 812 },
    deviceScaleFactor: 2,
  });
  try {
    await phone.route("**/*", (route) =>
      route.request().url().startsWith("http://127.0.0.1:4174/") ? route.continue() : route.abort(),
    );
    const page = await phone.newPage();
    await setLocale(page, "ja");
    await page.goto(pathFor(sample));
    await ready(page, "ja", true);
    await page.screenshot({ path: join(output, "report-ja-phone.png"), animations: "disabled" });
  } finally {
    await phone.close();
  }

  const temp = await mkdtemp(join(output, "video-"));
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:4174",
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: temp, size: { width: 1280, height: 720 } },
  });
  try {
    await context.route("**/*", (route) =>
      route.request().url().startsWith("http://127.0.0.1:4174/") ? route.continue() : route.abort(),
    );
    const page = await context.newPage();
    const started = Date.now();
    const video = page.video();
    if (!video) throw new Error("Video recording unavailable");
    const cues: Cue[] = [];
    const elapsed = () => (Date.now() - started) / 1000;
    const pause = (seconds = 1.5) => page.waitForTimeout(seconds * 1000);
    // Shows a caption in a bar at the bottom of the picture (outside the app's own DOM tree) and
    // holds it long enough to read: about 14 characters a second, at least 4 seconds.
    const say = async (caption: { en: string; ja: string }) => {
      const previous = cues.at(-1);
      if (previous) previous.end = elapsed();
      await page.evaluate(
        `(() => {
          let bar = document.getElementById("demo-caption");
          if (!bar) {
            bar = document.createElement("div");
            bar.id = "demo-caption";
            bar.setAttribute("aria-hidden", "true");
            bar.style.cssText = "position:fixed;left:0;right:0;bottom:0;z-index:100;padding:12px 32px;background:rgba(9,9,11,0.9);color:#fff;font:600 22px/1.45 'Segoe UI','Yu Gothic UI',system-ui,sans-serif;text-align:center";
            document.body.appendChild(bar);
          }
          bar.textContent = ${JSON.stringify(caption.en)};
        })()`,
      );
      cues.push({ start: elapsed(), end: 0, ...caption });
      await page.waitForTimeout(Math.max(4000, caption.en.length * 70));
    };
    const strings = CATALOGS.en;
    await page.goto("/");
    await ready(page, "en");
    await expect(page.getByRole("note")).toBeVisible();
    await say(CAPTIONS.intro);
    await page.getByRole("link", { name: sample.title }).click();
    await ready(page, "en", true);
    await say(CAPTIONS.sample);
    await top(page, strings.report.title);
    await say(CAPTIONS.report);
    const citationPrefix = strings.report.showLine.split("{line}")[0];
    await page
      .getByRole("region", { name: strings.report.title })
      .getByRole("button", { name: new RegExp(`^${citationPrefix}`) })
      .first()
      .click();
    await say(CAPTIONS.citation);
    await top(page, strings.review.title);
    await say(CAPTIONS.review);
    await page.getByRole("button", { name: strings.review.approve }).click();
    await expect(page.getByText(strings.replay.decisionNotSaved)).toBeVisible();
    await say(CAPTIONS.decision);
    await page.getByRole("link", { name: strings.investigation.back }).click();
    await ready(page, "en");
    await page.getByRole("link", { name: regression.title }).click();
    await ready(page, "en", true);
    await top(page, strings.report.title);
    await say(CAPTIONS.regression);
    await top(page, strings.review.title);
    await say(CAPTIONS.regressionReview);
    await page.getByRole("link", { name: strings.investigation.back }).click();
    await ready(page, "en");
    await page.getByRole("link", { name: abstention.title }).click();
    await ready(page, "en", true);
    await top(page, strings.report.title);
    await expect(page.getByText(strings.report.unknownBanner, { exact: true })).toBeVisible();
    await say(CAPTIONS.abstention);
    await page.getByRole("link", { name: strings.investigation.back }).click();
    await ready(page, "en");
    await page.getByLabel(strings.language.label, { exact: true }).selectOption("ja");
    await expect(
      page.getByRole("heading", { level: 1, name: CATALOGS.ja.overview.title }),
    ).toBeVisible();
    await say(CAPTIONS.japanese);
    await pause();
    const seconds = elapsed();
    const last = cues.at(-1);
    if (last) last.end = seconds;
    await context.close();
    const destination = join(output, "kensa-demo.webm");
    await video.saveAs(destination);
    const cache = dirname(dirname(dirname(browser.browserType().executablePath())));
    // Re-encode with Playwright's own cached ffmpeg (Windows build; nothing is downloaded), at a
    // constant quality chosen for sharp text rather than a small file.
    const ffmpegDir = readdirSync(cache).find((name) => name.startsWith("ffmpeg-"));
    if (!ffmpegDir) throw new Error("Playwright cached ffmpeg not found");
    const encoded = join(temp, "encoded.webm");
    execFileSync(
      join(cache, ffmpegDir, "ffmpeg-win64.exe"),
      [
        ...["-y", "-i", destination, "-c:v", "libvpx-vp9", "-crf", "28", "-b:v", "0"],
        ...["-row-mt", "1", "-an", encoded],
      ],
      { stdio: "ignore" },
    );
    await rm(destination);
    await rename(encoded, destination);
    await writeFile(join(output, "kensa-demo.en.vtt"), webVtt(cues, "en"), "utf8");
    await writeFile(join(output, "kensa-demo.ja.vtt"), webVtt(cues, "ja"), "utf8");
    await writeFile(join(output, "kensa-demo-transcript.md"), transcript(cues, seconds), "utf8");
  } finally {
    await context.close();
    await rm(temp, { recursive: true, force: true });
  }
  let total = 0;
  for (const name of (await readdir(output)).filter((name) => !name.startsWith(".")).sort()) {
    const size = (await stat(join(output, name))).size;
    total += size;
    console.log(`${name}: ${String(size)} bytes`);
  }
  // A guard against a runaway capture, not a quality target.
  expect(total).toBeLessThan(30_000_000);
});
