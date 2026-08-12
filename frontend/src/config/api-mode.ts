/**
 * Single source of truth for validating NEXT_PUBLIC_API_MODE.
 *
 * Two callers share this one pure function so the rule can't drift between
 * build time and app runtime:
 *  - `next.config.ts`, at config load, passing the `phase` argument Next's
 *    CLI hands it directly;
 *  - `app.config.ts`, at module evaluation, passing `process.env.NEXT_PHASE`
 *    (which Next sets during the build's page-data-collection step, and
 *    which is a genuine runtime lookup rather than a compile-time value).
 *
 * Phase is the gate, not NODE_ENV. `next build --debug-prerender` forces
 * NODE_ENV to "development" — Turbopack inlines that as a compile-time
 * literal into the resulting chunks — but it does not and cannot change
 * which phase Next itself is running: every `next build` invocation, with
 * or without that flag, runs as PHASE_PRODUCTION_BUILD. Measured in
 * reports/frontend-audit/report_v3.md (F-01), which is the bypass this
 * closes.
 */

import { PHASE_PRODUCTION_BUILD } from "next/constants";

export type ApiMode = "http" | "mock";

export function resolveApiMode(value: string | undefined, phase: string | undefined): ApiMode {
  if (value === undefined || value === "") return "http";
  if (value !== "http" && value !== "mock") {
    throw new Error('NEXT_PUBLIC_API_MODE must be exactly "http" or "mock".');
  }
  if (value === "mock" && phase === PHASE_PRODUCTION_BUILD) {
    throw new Error(
      `NEXT_PUBLIC_API_MODE=mock is not permitted during a production build (Next phase "${PHASE_PRODUCTION_BUILD}"). ` +
        "Mock authentication (localStorage-only login) must never ship to production. This checks Next's real " +
        'build phase, not NODE_ENV: `next build --debug-prerender` forces NODE_ENV to "development" as a ' +
        "compile-time-inlined literal inside the compiled bundle, but it cannot change the phase Next itself is running.",
    );
  }
  return value;
}
