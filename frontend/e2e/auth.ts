import { expect, type Page } from "@playwright/test";

const MOCK_PASSWORD = "correct-horse";

type MockAccount =
  | { kind: "fresh"; name: string }
  | { kind: "returning"; email: string };

/**
 * Authenticates through mock mode's public UI contract.
 *
 * The visible mode assertion is the safety boundary: this helper refuses to
 * submit credentials to an HTTP-backed build. Fresh accounts use the mock-only
 * approved-invite URL exposed by the waitlist page, while returning accounts
 * use ordinary sign-in. No production session storage details live in tests.
 */
export async function authenticateMockUser(page: Page, account: MockAccount): Promise<void> {
  await page.goto("/login");
  await expect(page.getByText(/No data leaves your browser\./)).toBeVisible();

  if (account.kind === "fresh") {
    await page.goto("/signup?approvalToken=demo-approved");
    await page.getByLabel("Name").fill(account.name);
    await page.getByRole("textbox", { name: "Password" }).fill(MOCK_PASSWORD);
    await page.getByRole("button", { name: "Create my workspace" }).click();
  } else {
    await page.getByLabel("Email").fill(account.email);
    await page.getByRole("textbox", { name: "Password" }).fill(MOCK_PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
  }

  await expect(page).toHaveURL(/\/app$/);
}
