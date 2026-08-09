import { expect, test, type Page } from "@playwright/test";

async function loginToDemo(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("demo@example.com");
  await page.getByRole("textbox", { name: "Password" }).fill("correct-horse");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

test("date filtering stays selected and History does not overflow at phone width", async ({
  page,
}) => {
  await loginToDemo(page);
  await page.goto("/app/history");
  await expect(
    page.getByRole("main").getByRole("link", { name: /UK market entry.*312k tokens/ }),
  ).toBeVisible();

  const recent = page.getByRole("radio", { name: "Last 7 days" });
  await recent.click();
  await expect(recent).toHaveAttribute("aria-checked", "true");

  await page.setViewportSize({ width: 390, height: 844 });
  const widths = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(widths.content).toBe(widths.viewport);
});
