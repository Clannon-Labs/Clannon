import { expect, test } from "@playwright/test";
import { authenticateMockUser } from "./auth";

test("date filtering stays selected and History does not overflow at phone width", async ({
  page,
}) => {
  await authenticateMockUser(page, { kind: "returning", email: "demo@example.com" });
  await page.goto("/app/history");
  await expect(
    page.getByRole("main").getByRole("link", { name: /UK market entry.*312k tokens/ }),
  ).toBeVisible();

  const recent = page.getByRole("radio", { name: "Last 7 days" });
  await recent.click();
  await expect(recent).toHaveAttribute("aria-checked", "true");

  await page.setViewportSize({ width: 390, height: 844 });
  // AppShell intentionally animates its desktop sidebar margin for 300 ms.
  // Resizing during a test can sample that transition halfway through, when
  // the content is temporarily offset even though the settled phone layout
  // fits exactly. Wait for settlement; never relax the equality itself.
  await expect.poll(async () => page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }))).toEqual({ viewport: 390, content: 390 });
});
