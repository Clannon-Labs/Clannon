import { expect, test } from "@playwright/test";

const PARTIAL_BRIEF =
  "Force a partial timeout for e2e — draft a short market note on EU solar subsidies for a client presentation.";

async function signup(page: import("@playwright/test").Page, email: string) {
  await page.goto("/signup");
  await page.getByLabel("Name").fill("Priya Nair");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("textbox", { name: "Password" }).fill("correct-horse");
  await page.getByRole("button", { name: "Create my workspace" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

async function throughFirstRunGuide(page: import("@playwright/test").Page) {
  await page.getByLabel("Client or project").fill("Solveig · EU expansion");
  await page.getByLabel("What decision or outcome do you need?").fill(
    "Decide whether EU solar subsidy changes affect our Q4 pricing.",
  );
  await page.getByRole("button", { name: "Build editable brief" }).click();
  await expect(page.getByRole("textbox", { name: "Message" })).toHaveValue(/Solveig/);
}

test("a partial-timeout delivery renders the completion badge and banner, and Continue works", async ({
  page,
}) => {
  // a full mock delivery takes ~1.2 minutes end to end (FIRST_VALUE.md) — the
  // default 30s per-test timeout isn't enough to watch one run to terminal.
  test.setTimeout(150_000);
  await signup(page, `partial-${Date.now()}@example.com`);
  await throughFirstRunGuide(page);

  const composer = page.getByRole("textbox", { name: "Message" });
  await composer.fill(PARTIAL_BRIEF);
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page).toHaveURL(/\/app\/runs\/run_/, { timeout: 20_000 });

  // exact: true — the run's own title ("Force a partial timeout for e2e…")
  // otherwise substring-matches "Partial" in the sidebar/breadcrumb/palette too
  await expect(page.getByText("Partial", { exact: true })).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("Ran out of time before finishing")).toBeVisible();
  await expect(
    page.getByText(/ask it to continue and it'll pick up where it stopped/),
  ).toBeVisible();

  // it is a partial *delivery*, not a failure — the status pill must read
  // Delivered, and the report itself must still be there to read
  await expect(page.getByText("Delivered", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Report" })).not.toBeEmpty();

  await page.screenshot({
    path: "previews/2026-07-28_completion-status/desktop-partial-run.png",
    fullPage: true,
  });

  const continueButton = page.getByRole("button", { name: "Continue this run" });
  await expect(continueButton).toBeVisible();
  await continueButton.click();
  await expect(composer).toBeFocused();
});

test("the partial banner reads correctly at 390px", async ({ page }) => {
  test.setTimeout(150_000);
  await page.setViewportSize({ width: 390, height: 844 });
  await signup(page, `partial-mobile-${Date.now()}@example.com`);
  await throughFirstRunGuide(page);

  const composer = page.getByRole("textbox", { name: "Message" });
  await composer.fill(PARTIAL_BRIEF);
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page).toHaveURL(/\/app\/runs\/run_/, { timeout: 20_000 });

  // exact: true — the run's own title ("Force a partial timeout for e2e…")
  // otherwise substring-matches "Partial" in the sidebar/breadcrumb/palette too
  await expect(page.getByText("Partial", { exact: true })).toBeVisible({ timeout: 120_000 });
  await expect(page.getByRole("button", { name: "Continue this run" })).toBeVisible();

  await page.screenshot({
    path: "previews/2026-07-28_completion-status/mobile-390-partial-run.png",
    fullPage: true,
  });
});

test("a filter-blocked run explains the gate, preserves the brief, and offers a way forward", async ({
  page,
}) => {
  // the block check only fires after the full scripted work sequence runs
  // (same ~70-90s as a normal delivery) — it diverges only at the very end.
  test.setTimeout(150_000);
  await signup(page, `blocked-${Date.now()}@example.com`);
  await throughFirstRunGuide(page);

  const composer = page.getByRole("textbox", { name: "Message" });
  await composer.fill(
    "Force a blocked output for e2e — draft a short market note on EU solar subsidies.",
  );
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page).toHaveURL(/\/app\/runs\/run_/, { timeout: 20_000 });

  await expect(page.getByText("Blocked", { exact: true })).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("Held back by the output filter")).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit and resubmit" })).toBeVisible();

  // no partial claim over a run that never produced a draft to check
  await expect(page.getByText("Partial", { exact: true })).toHaveCount(0);

  await page.screenshot({
    path: "previews/2026-07-28_completion-status/desktop-blocked-run.png",
    fullPage: true,
  });
});
