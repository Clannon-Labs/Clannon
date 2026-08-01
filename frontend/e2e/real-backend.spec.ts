import { expect, test, type Page } from "@playwright/test";

const project = "Northstar · Nepal launch";
const decision = "Decide whether to launch the research service in Nepal this quarter";
const context =
  "Budget is $80,000. Target customers are export-focused agencies. Prefer a staged launch.";

async function removeDevelopmentIndicator(page: Page) {
  await page.locator("nextjs-portal").evaluateAll((portals) => {
    portals.forEach((portal) => portal.remove());
  });
}

async function signup(page: Page, email: string) {
  await page.goto("/signup");
  await page.getByLabel("Name").fill("Asha Rai");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("textbox", { name: "Password" }).fill("correct-horse");
  await page.getByRole("button", { name: "Create my workspace" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

test("real backend: paid desktop journey reaches durable delivery", async ({ page }) => {
  test.setTimeout(600_000);
  const browserErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));

  await signup(page, `paid-desktop-${Date.now()}@example.com`);
  await expect(page.getByText("Start with a project")).toBeVisible();

  // real backend + a paid-ish plan is expected here (this suite targets a
  // live account, not the free-tier default) — the New Project dialog's
  // goal/context fields only render when the plan includes wiki; if this
  // account is free-tier only "Project name" will be present and this will
  // correctly fail loudly rather than silently skip the assertion.
  await page.getByRole("button", { name: "Create your first project" }).click();
  await page.getByLabel("Project name").fill(project);
  await page.getByLabel(/What's the goal for this project/).fill(decision);
  await page.getByLabel("Tell Clannon about this client").fill(context);
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByRole("button", { name: `Project ${project}` })).toBeVisible();

  await page.goto("/app/memory");
  await expect(page.getByRole("heading", { name: "The archive" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Goal for this project" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Client: Northstar · Nepal launch/ })).toBeVisible();

  await page.goto("/app/settings?tab=models");
  await expect(page.getByRole("heading", { name: "Your setup" })).toBeVisible();
  await expect(page.getByText("Pick a model per role")).toBeVisible();

  await page.goto("/app");
  const composer = page.getByRole("textbox", { name: "Message" });
  await removeDevelopmentIndicator(page);
  await composer.fill(
    `For ${project}, prepare a decision memo. ${decision}. ${context} Cite material claims and separate facts from assumptions.`,
  );
  await page
    .getByLabel("Attach files — text, PDF, image, audio, or video")
    .setInputFiles("previews/2026-07-28_first-value-pass/after/first-assignment-390x844.png");
  await expect(page.getByText("first-assignment-390x844.png")).toBeVisible();

  await page.getByRole("button", { name: "Send" }).click();
  await expect(page).toHaveURL(/\/app\/runs\/run_/, { timeout: 20_000 });
  await expect(page.getByText("first-assignment-390x844.png")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByLabel("Stop the run")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Safe to leave this page — work continues.")).toBeVisible();

  await removeDevelopmentIndicator(page);
  await page.screenshot({
    path: "previews/2026-07-28_real-backend-pass/after/live-run-1280x800.png",
    fullPage: true,
  });

  const reply = page.getByRole("textbox", { name: "Message" });
  await reply.fill("Narrow the recommendation to agencies with fewer than 20 employees.");
  await page.reload();
  await expect(page.getByText("first-assignment-390x844.png")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("textbox", { name: "Message" })).toHaveValue(
    "Narrow the recommendation to agencies with fewer than 20 employees.",
  );

  await expect(page.getByLabel("Copy report as markdown")).toBeVisible({ timeout: 540_000 });
  await expect(page.getByRole("region", { name: "Report" })).not.toBeEmpty();
  await expect(page.getByLabel("Stop the run")).toHaveCount(0);

  await page.reload();
  await expect(page.getByLabel("Copy report as markdown")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("first-assignment-390x844.png")).toBeVisible();

  await page.goto("/app/settings?tab=usage");
  await expect(page.getByRole("progressbar", { name: "Token budget used this period" })).toBeVisible();

  expect(browserErrors).toEqual([]);
});

test("real backend: paid journey remains usable at 390px", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signup(page, `paid-mobile-${Date.now()}@example.com`);

  await page.getByRole("button", { name: "Open menu" }).click();
  await page.getByRole("link", { name: "Memory" }).click();
  await expect(page.getByRole("heading", { name: "The archive" })).toBeVisible();

  await removeDevelopmentIndicator(page);
  await page.screenshot({
    path: "previews/2026-07-28_real-backend-pass/before/memory-390x844.png",
    fullPage: true,
  });
});

test("real backend: resume an existing run from browser history", async ({ page }) => {
  const resumeEmail = process.env.REAL_BACKEND_RESUME_EMAIL;
  const resumeRunId = process.env.REAL_BACKEND_RESUME_RUN_ID;
  test.skip(!resumeEmail || !resumeRunId, "Set resume account and run ID.");
  test.setTimeout(60_000);

  await page.goto("/login");
  await page.getByLabel("Email").fill(resumeEmail!);
  await page.getByRole("textbox", { name: "Password" }).fill("correct-horse");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(`/app/runs/${resumeRunId}`);

  await expect(page.getByText("first-assignment-390x844.png")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByLabel("Copy report as markdown")).toBeVisible({ timeout: 30_000 });
  const report = page.getByRole("region", { name: "Report" });
  await expect(report).not.toBeEmpty();

  const reportBox = await report.boundingBox();
  if (reportBox && reportBox.height > 1_600) {
    await page.evaluate((y) => window.scrollTo(0, y), reportBox.y + 1_000);
    await expect
      .poll(async () => (await report.locator("header").boundingBox())?.y ?? 999)
      .toBeLessThan(2);
    await page.screenshot({
      path: "previews/2026-07-28_real-backend-pass/after/long-report-controls-1280x800.png",
    });
  }

  await removeDevelopmentIndicator(page);
  await page.screenshot({
    path: "previews/2026-07-28_real-backend-pass/after/delivered-recovery-1280x800.png",
    fullPage: true,
  });
});
