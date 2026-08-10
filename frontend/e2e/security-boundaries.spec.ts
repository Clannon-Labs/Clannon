import { expect, test } from "@playwright/test";

async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("security-preview@example.com");
  await page.getByRole("textbox", { name: "Password" }).fill("correct-horse");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/app$/, { timeout: 20_000 });
}

test("production CSP forbids frames and opens PDF blob in browser viewer", async ({ page }) => {
  const cspErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" && /content security policy/i.test(message.text())) {
      cspErrors.push(message.text());
    }
  });

  await login(page);
  await page.goto("/app/runs/run_seed_1");
  await page.getByTitle("Preview source-pack.pdf").click();

  const previewLink = page.getByRole("link", { name: "Open PDF preview" });
  await expect(previewLink).toHaveAttribute("href", /^blob:/);
  await expect(page.locator("iframe")).toHaveCount(0);
  const popupPromise = page.waitForEvent("popup");
  await previewLink.click();
  const popup = await popupPromise;
  await expect.poll(() => popup.url().startsWith("blob:")).toBe(true);
  await popup.close();
  await expect.poll(() => cspErrors).toEqual([]);
});

test("production build without API mode remains HTTP-backed", async ({ page }) => {
  test.skip(
    process.env.CLANNON_PRODUCTION_HTTP_PROOF !== "1",
    "Runs only against the production bundle built without NEXT_PUBLIC_API_MODE.",
  );

  const backendRequests: string[] = [];
  await page.addInitScript(() => {
    localStorage.setItem(
      "clannon.mock.session",
      JSON.stringify({
        id: "mock-bypass",
        name: "Mock bypass",
        email: "bypass@example.com",
        plan: "pro",
      }),
    );
  });
  await page.route("http://127.0.0.1:38111/**", async (route) => {
    backendRequests.push(route.request().url());
    await route.fulfill({
      status: route.request().url().endsWith("/auth/me") ? 401 : 500,
      contentType: "application/json",
      headers: {
        "Access-Control-Allow-Origin": "http://127.0.0.1:3100",
        "Access-Control-Allow-Credentials": "true",
      },
      body: JSON.stringify({ detail: "proof response" }),
    });
  });

  await page.goto("/app");
  await expect.poll(() => backendRequests.some((url) => url.endsWith("/auth/me"))).toBe(true);
  await expect(page).toHaveURL(/\/login$/);
});
