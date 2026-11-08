import { expect, test, type APIRequestContext } from "@playwright/test";

import { CATALOGS, expectNoSeriousViolations, useLocale } from "./axe";

// A corroborated rules-only run pauses for the operator's decision on its proposals (M3).
async function createAwaitingApproval(
  request: APIRequestContext,
  sampleId: string,
): Promise<string> {
  const created = await request.post("/api/investigations", {
    data: { sample_id: sampleId, provider: "mock" },
  });
  expect(created.status()).toBe(201);
  const { id } = (await created.json()) as { id: string };
  await expect
    .poll(
      async () => {
        const response = await request.get(`/api/investigations/${id}`);
        return ((await response.json()) as { status: string }).status;
      },
      { timeout: 30_000 },
    )
    .toBe("awaiting_approval");
  return id;
}

test("a sample investigation runs end to end and its citation opens the log line", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Overview" })).toBeVisible();
  await page
    .getByRole("navigation", { name: "Main" })
    .getByRole("link", { name: "New investigation" })
    .click();

  await page.getByLabel("Sample incident").check();
  await page.getByLabel("Sample", { exact: true }).selectOption("missing-env-var");
  await page.getByLabel(/Rules only/).check();
  await page.getByRole("button", { name: "Investigate" }).click();

  await expect(page).toHaveURL(/\/investigations\/[0-9a-f-]{36}$/);
  await expect(page.getByText("Awaiting approval", { exact: true })).toBeVisible({
    timeout: 30_000,
  });
  const report = page.getByRole("region", { name: "Diagnosis" });
  await expect(report.getByText("Cause corroborated", { exact: true })).toBeVisible();
  await expect(report.getByText("Missing environment variable").first()).toBeVisible();

  const timeline = page.getByRole("region", { name: "Agent timeline" });
  await expect(timeline.getByText("Report", { exact: true })).toBeVisible();

  await report
    .getByRole("button", { name: /Show line \d+ in the log/ })
    .first()
    .click();
  await expect(page.locator('[aria-current="location"]')).toContainText("VITE_API_BASE_URL");

  // Human in the loop: approving records the decision; the paused run then finishes.
  const review = page.getByRole("region", { name: "Remediation review" });
  await expect(review.getByText("Template").first()).toBeVisible();
  await review.getByLabel("Note (optional)").fill("Checked against the log.");
  await review.getByRole("button", { name: "Approve proposals" }).click();
  await expect(page.getByText("Completed", { exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(review.getByText(/^Approved on /)).toBeVisible();
  await expect(review.getByText(/Not applied: apply the approved changes yourself/)).toBeVisible();
  await expect(review.getByRole("button", { name: "Approve proposals" })).toHaveCount(0);
  await expect(timeline.getByText("Record decision", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: /All investigations/ }).click();
  await expect(page.getByRole("table", { name: "Recent investigations" })).toContainText(
    "Frontend build fails an environment check",
  );
});

test("pasted secrets are redacted before they are shown", async ({ page }) => {
  const token = "ghp_" + "Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op8Qr9St0Uv1Wx2";
  await page.goto("/investigations/new");
  await page
    .getByLabel("Failed CI log")
    .fill(
      `##[group]Run deploy\nexport GITHUB_TOKEN=${token}\nError: Missing required environment variable: API_URL\n##[error]Process completed with exit code 1.`,
    );
  await page.getByLabel(/Rules only/).check();
  await page.getByRole("button", { name: "Investigate" }).click();
  await expect(page.getByText("Awaiting approval", { exact: true })).toBeVisible({
    timeout: 30_000,
  });
  await page.getByRole("button", { name: "Show full log" }).click();
  await expect(page.getByRole("region", { name: "Log lines" })).toContainText("[REDACTED:");
  await expect(page.locator("body")).not.toContainText(token);
});

test("the skip link moves keyboard focus to the main content", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to main content" });
  await expect(skip).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("main#main")).toBeFocused();
});

for (const [scheme, locale] of [
  ["light", "en"],
  ["dark", "en"],
  ["light", "ja"],
  ["dark", "ja"],
] as const) {
  test(`main pages have no serious accessibility violations (${scheme}, ${locale})`, async ({
    page,
    request,
  }) => {
    const strings = CATALOGS[locale];
    await useLocale(page, locale);
    await page.emulateMedia({ colorScheme: scheme });
    const id = await createAwaitingApproval(request, "db-connection");
    for (const [label, path] of [
      ["overview", "/"],
      ["new investigation", "/investigations/new"],
      ["investigation", `/investigations/${id}`],
    ] as const) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("lang", locale);
      if (label === "investigation") {
        await expect(page.getByRole("region", { name: strings.report.title })).toBeVisible();
        await expect(page.getByRole("region", { name: strings.log.region })).toBeVisible();
        await expect(page.getByRole("region", { name: strings.review.title })).toBeVisible();
      }
      await expectNoSeriousViolations(page, `${label} (${scheme}, ${locale})`);
    }
  });
}
