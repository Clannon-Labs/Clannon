import { appConfig } from "@/config/app.config";

/**
 * Shown only while the app runs against the mock simulator, so demo
 * visitors aren't confused and real deploys never show it.
 */
export const apiModeNotice =
  appConfig.apiMode === "mock" ? (
    <p className="mt-6 rounded-md border border-memory/25 bg-memory-soft px-4 py-3 text-[13px] leading-relaxed text-memory">
      Demo mode — any email and an 8+ character password signs you into a
      simulated workspace. No data leaves your browser.
    </p>
  ) : null;
