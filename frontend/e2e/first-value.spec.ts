import { expect, test, type Page } from "@playwright/test";

const decision = "Decide whether to enter the UK market this year";

async function signup(page: Page) {
  await page.goto("/signup");
  await page.getByLabel("Name").fill("Maya Chen");
  await page.getByLabel("Email").fill("maya@example.com");
  await page.getByRole("textbox", { name: "Password" }).fill("correct-horse");
  await page.getByRole("button", { name: "Create my workspace" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

async function removeDevelopmentIndicator(page: Page) {
  await page.locator("nextjs-portal").evaluateAll((portals) => {
    portals.forEach((portal) => portal.remove());
  });
}

test("new user reaches a live, scoped assignment without prompt expertise", async ({ page }) => {
  test.setTimeout(90_000);
  const browserErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));

  await signup(page);

  await expect(page.getByRole("heading", { name: "Start with decision, not prompt craft." })).toBeVisible();
  await expect(page.getByText("Meridian")).toHaveCount(0);
  await expect(page.getByText("First assignment")).toBeVisible();

  await page.getByLabel("Client or project").fill("Acme · UK expansion");
  await page.getByLabel("What decision or outcome do you need?").fill(decision);
  await page
    .getByLabel("Useful context or constraints (optional)")
    .fill("Budget is £250k. Launch must happen before October.");
  await page.getByRole("button", { name: "Comparison" }).click();
  await page.getByRole("button", { name: "Build editable brief" }).click();

  const composer = page.getByRole("textbox", { name: "Message" });
  await expect(composer).toHaveValue(/For Acme · UK expansion, prepare a comparison\./);
  await expect(composer).toHaveValue(new RegExp(decision));
  await expect(composer).toHaveValue(/Cite every material claim/);

  await removeDevelopmentIndicator(page);
  await page.screenshot({
    path: "previews/2026-07-28_first-value-pass/after/editable-brief-1280x800.png",
    fullPage: true,
  });

  await page.getByRole("button", { name: "Send" }).click();
  await expect(page).toHaveURL(/\/app\/runs\/run_/, { timeout: 20_000 });
  await expect(page.getByRole("button", { name: "Project Acme · UK expansion" })).toBeVisible();
  await expect(
    page.getByRole("link", { name: /For Acme · UK expansion, prepare a comparison/ }),
  ).toBeVisible();
  await expect(page.getByRole("main").getByText("Clannon", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Stop the run")).toBeVisible();
  await expect(page.getByText(decision, { exact: false })).toBeVisible();
  await expect(page.getByLabel("Copy report as markdown")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByLabel("Stop the run")).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Report" })).toContainText("Recommendation");

  expect(browserErrors).toEqual([]);
});

test("first assignment remains usable at phone width", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signup(page);

  await expect(page.getByRole("heading", { name: "Start with decision, not prompt craft." })).toBeVisible();
  await page.getByLabel("Client or project").fill("Acme mobile");
  await page.getByLabel("What decision or outcome do you need?").fill(decision);
  await expect(page.getByRole("button", { name: "Build editable brief" })).toBeEnabled();

  await removeDevelopmentIndicator(page);
  await page.screenshot({
    path: "previews/2026-07-28_first-value-pass/after/first-assignment-390x844.png",
    fullPage: true,
  });
});
