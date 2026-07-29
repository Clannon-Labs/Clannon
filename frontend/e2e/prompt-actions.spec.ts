import { expect, test } from "@playwright/test";

const ORIGINAL =
  "Client is a US-based DTC skincare brand (~$6M ARR) considering UK expansion in Q4. Need: market size and structure, regulatory requirements post-Brexit, recent comparable entrants and how they performed, and a go/no-go recommendation with budget.";

async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("returning@example.com");
  await page.getByRole("textbox", { name: "Password" }).fill("correct-horse");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/app$/, { timeout: 20_000 });
}

test("sent prompt owns copy and edit actions, and revision starts a new path", async ({ page }) => {
  test.setTimeout(90_000);
  await login(page);
  await page.goto("/app/runs/run_seed_1");

  const prompt = page.getByRole("button", {
    name: /Client is a US-based DTC skincare brand.*show prompt actions/i,
  });
  await prompt.hover();
  await expect(page.getByRole("button", { name: "Copy sent prompt" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit sent prompt" })).toBeVisible();
  await page.getByRole("button", { name: "Copy sent prompt" }).click();
  await expect(page.getByRole("tooltip", { name: "Copied" })).toBeVisible();

  await page.getByRole("button", { name: "Edit sent prompt" }).click();
  const editor = page.getByRole("textbox", { name: "Edit sent prompt" });
  await expect(editor).toHaveValue(ORIGINAL);
  await expect(page.getByText(/starts a new path from here/i)).toBeVisible();
  await page.screenshot({
    path: "previews/2026-07-29_prompt-revision/desktop-edit-prompt.png",
    fullPage: true,
  });

  await editor.fill("Compare UK and German entry requirements for the same client.");
  await page.getByRole("button", { name: "Restart from here" }).click();
  await expect(page).toHaveURL(/\/app\/runs\/run_(?!seed_1)/);
  await expect(
    page.getByRole("button", {
      name: /Compare UK and German entry requirements.*show prompt actions/i,
    }),
  ).toBeVisible();
  await expect(page.getByText(ORIGINAL, { exact: true })).toHaveCount(0);
  await page.screenshot({
    path: "previews/2026-07-29_prompt-revision/desktop-revised-path.png",
    fullPage: true,
  });
});

test("touch users reveal the same prompt actions by tapping the bubble", async ({ page }) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await page.goto("/app/runs/run_seed_1");

  await page.getByRole("button", {
    name: /Client is a US-based DTC skincare brand.*show prompt actions/i,
  }).click();
  await expect(page.getByRole("button", { name: "Copy sent prompt" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit sent prompt" })).toBeVisible();
  await page.screenshot({
    path: "previews/2026-07-29_prompt-revision/mobile-tap-actions.png",
    fullPage: true,
  });
});
