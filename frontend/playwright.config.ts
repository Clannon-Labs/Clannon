import { defineConfig } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3100";
const webServerURL = new URL(baseURL);
// Live-backend journeys need an explicitly prepared backend/account and stay
// outside the deterministic mock suite. Opt in together with an external
// PLAYWRIGHT_BASE_URL and PLAYWRIGHT_SKIP_WEB_SERVER=1.
const includeRealBackend = process.env.PLAYWRIGHT_INCLUDE_REAL_BACKEND === "1";

export default defineConfig({
  testDir: "./e2e",
  testIgnore: includeRealBackend ? undefined : "**/real-backend.spec.ts",
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    baseURL,
    viewport: { width: 1280, height: 800 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    launchOptions: {
      executablePath: "/usr/bin/google-chrome",
    },
  },
  webServer: process.env.PLAYWRIGHT_SKIP_WEB_SERVER
    ? undefined
    : {
        command:
          `NEXT_PUBLIC_API_MODE=mock NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run dev -- --hostname ${webServerURL.hostname} --port ${webServerURL.port || "3000"}`,
        url: `${baseURL}/signup`,
        reuseExistingServer: true,
        timeout: 120_000,
      },
});
