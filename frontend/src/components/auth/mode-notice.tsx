import { appConfig } from "@/config/app.config";

/**
 * Shown only while the app runs against the mock simulator, so demo
 * visitors aren't confused and real deploys never show it.
 */
/* neutral on purpose: amber belongs to memory alone, and a system notice
   must not outrank the page's own CTA */
export const apiModeNotice =
  appConfig.apiMode === "mock" ? (
    <p className="mt-6 rounded-md border border-border bg-surface px-4 py-3 text-[13px] leading-relaxed text-muted-foreground">
      <span className="mr-2 font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-faint">
        Demo
      </span>
      Any email and an 8+ character password signs you into a simulated
      workspace. No data leaves your browser.
    </p>
  ) : null;
