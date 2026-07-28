import { expect, test } from "@playwright/test";

test("landing remains polished without client-owned marketing interactions", async ({ page }) => {
  const browserErrors: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));

  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Hand off the legwork/ })).toBeVisible();
  await expect(page.getByText("DECISION LOG — LIVE")).toBeVisible();

  const theme = page.getByRole("button", { name: "Change color theme" });
  await theme.click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  const menu = page.locator("[data-mobile-menu]");
  await page.getByLabel("Open menu").focus();
  await page.keyboard.press("Enter");
  await expect(menu).toHaveAttribute("open", "");
  await page.keyboard.press("Escape");
  await expect(menu).not.toHaveAttribute("open", "");

  await page.getByLabel("Open menu").click();
  await page.getByRole("navigation", { name: "Mobile" }).getByRole("link", { name: "Memory" }).click();
  await expect(page).toHaveURL(/#memory$/);
  await expect(menu).not.toHaveAttribute("open", "");

  expect(browserErrors).toEqual([]);
});
