import { expect, test, type Page } from "@playwright/test";
import { authenticateMockUser } from "./auth";

const previewRoot = "previews/2026-08-01_fixed-billing-contract/after";
const billingE2EEmail = process.env.BILLING_E2E_EMAIL;

async function authenticate(page: Page) {
  if (billingE2EEmail) {
    await page.goto("/login");
    await page.getByLabel("Email").fill(billingE2EEmail);
    await page.getByRole("textbox", { name: "Password" }).fill("correct-horse");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/app$/);
    return;
  }
  await authenticateMockUser(page, { kind: "fresh", name: "Billing Review" });
}

async function removeDevelopmentIndicator(page: Page) {
  await page.locator("nextjs-portal").evaluateAll((portals) => {
    portals.forEach((portal) => portal.remove());
  });
}

test("usage, pending checkout, and root 402 remain actionable and honest", async ({ page }) => {
  const browserErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));
  await authenticate(page);

  if (billingE2EEmail) {
    await page.route("**/usage", (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        periodStart: "2026-07-31",
        periodEnd: "2026-08-31",
        periodEndExclusive: true,
        baseBudget: 100_000,
        additionalCredits: 50_000,
        budget: 150_000,
        used: 110_000,
        cacheReadTokens: 32_000,
        cacheWriteTokens: 4_000,
        byDay: [
          { date: "2026-07-31", tokens: 60_000 },
          { date: "2026-08-01", tokens: 50_000 },
        ],
      }),
    }));
  }
  await page.goto("/app/settings?tab=usage");
  await expect(page.getByText("Daily spend — current period")).toBeVisible();
  if (billingE2EEmail) {
    await expect(page.getByText(/confirmed add-on 50k/)).toBeVisible();
  } else {
    // Browser-created mock checkouts correctly stay pending: only the
    // server/operator contract can confirm credits and change entitlement.
    await expect(page.getByText("0 of 100k tokens")).toBeVisible();
    await expect(page.getByText(/confirmed add-on/)).toHaveCount(0);
  }
  await expect(page.getByText(/per-call hard stops are not live yet/)).toBeVisible();
  await removeDevelopmentIndicator(page);
  await page.screenshot({ path: `${previewRoot}/usage-1280x800.png`, fullPage: true });

  await page.goto("/app/settings?tab=billing");
  await expect(page.getByText(/Maximum 20M credits per checkout/)).toBeVisible();
  await page.getByLabel("Add-on token credits").fill("250000");
  await page.getByRole("button", { name: "Create add-on checkout" }).click();
  await expect(page.getByText("Add-on checkout created")).toBeVisible();
  await expect(page.getByText("pending", { exact: true })).toBeVisible();
  await removeDevelopmentIndicator(page);
  await page.screenshot({ path: `${previewRoot}/billing-pending-1280x800.png`, fullPage: true });

  await page.route("**/runs", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    await route.fulfill({
      status: 402,
      contentType: "application/json",
      body: JSON.stringify({
        detail: {
          code: "token_budget_exhausted",
          message: "Token budget exhausted for this billing period.",
          used: 100_000,
          budget: 100_000,
          periodEnd: "2026-08-31",
          periodEndExclusive: true,
          actions: [
            { kind: "add_on", endpoint: "/billing/checkout" },
            { kind: "upgrade", endpoint: "/billing/checkout" },
          ],
        },
      }),
    });
  });
  await page.goto("/app");
  await page.getByRole("textbox", { name: "Message" }).fill(
    "Force budget exhausted admission for e2e — verify the actionable refusal.",
  );
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByRole("link", { name: "Add token credits" })).toBeVisible();
  await expect(page.getByRole("link", { name: "See upgrade plans" })).toBeVisible();
  await expect(page.getByText(/reset on/)).toBeVisible();
  await removeDevelopmentIndicator(page);
  await page.screenshot({ path: `${previewRoot}/budget-402-1280x800.png`, fullPage: true });

  // Chromium may log the deliberately mocked 402 as a failed resource. That is
  // the behavior under test, not a browser/runtime defect; every other error stays fatal.
  expect(browserErrors.filter((message) => !message.includes("status of 402"))).toEqual([]);
});

test("usage and billing remain readable at 390px", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate(page);

  await page.goto("/app/settings?tab=usage");
  await expect(page.getByText("Daily spend — current period")).toBeVisible();
  await removeDevelopmentIndicator(page);
  await page.screenshot({ path: `${previewRoot}/usage-390x844.png`, fullPage: true });

  await page.goto("/app/settings?tab=billing");
  await expect(page.getByRole("button", { name: "Create add-on checkout" })).toBeVisible();
  await removeDevelopmentIndicator(page);
  await page.screenshot({ path: `${previewRoot}/billing-390x844.png`, fullPage: true });
});
