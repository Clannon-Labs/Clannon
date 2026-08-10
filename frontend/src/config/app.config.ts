/**
 * Clannon frontend configuration — the single file to edit when
 * wiring this UI to a real backend.
 *
 * Everything here can be overridden per-environment via NEXT_PUBLIC_*
 * variables (see .env.example). HTTP is the fail-safe default; mock mode
 * requires an explicit NEXT_PUBLIC_API_MODE=mock opt-in. Point
 * NEXT_PUBLIC_API_BASE_URL at the FastAPI host to change backends. No component
 * imports an URL or fetch call directly — they only know the client
 * in `src/lib/api`.
 */

import { requireHttpBaseUrl } from "@/config/url-policy";

export type ApiMode = "mock" | "http";

const env = {
  apiMode: process.env.NEXT_PUBLIC_API_MODE,
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL,
  wsBaseUrl: process.env.NEXT_PUBLIC_WS_BASE_URL,
  appUrl: process.env.NEXT_PUBLIC_APP_URL,
};

/**
 * Missing mode uses the real server. Mock authentication is intentionally
 * explicit: a typo must stop the build instead of shipping a convincing local
 * simulator to production.
 */
export function resolveApiMode(value: string | undefined): ApiMode {
  if (value === undefined || value === "") return "http";
  if (value === "http" || value === "mock") return value;
  throw new Error('NEXT_PUBLIC_API_MODE must be exactly "http" or "mock".');
}

export const appConfig = {
  /** "mock" runs the bundled simulator; "http" talks to the real backend. */
  apiMode: resolveApiMode(env.apiMode),

  /** Base URL of the backend — the Vraksha engine (FastAPI). No trailing slash. */
  apiBaseUrl: requireHttpBaseUrl(
    env.apiBaseUrl ?? "http://localhost:8000",
    "NEXT_PUBLIC_API_BASE_URL",
  ),

  /**
   * Origin the workspace is served from. Empty = same origin as the marketing
   * site, so workspace links stay relative (/app). Set NEXT_PUBLIC_APP_URL to
   * https://app.clannon.com to move the workspace to a subdomain — every
   * marketing→workspace link routes through `workspaceUrl()`, so that one env
   * var is the whole switch (the backend's auth cookie must then be scoped to
   * the parent domain — see the backend proposal).
   */
  appUrl: env.appUrl?.replace(/\/$/, "") ?? "",

  /**
   * Route table. If a backend route is renamed, change it here only.
   * `:id` segments are substituted by the http client.
   */
  endpoints: {
    /** Public, GET-only backend config (plans, features, limits). */
    config: "/config",
    login: "/auth/login",
    signup: "/auth/signup",
    logout: "/auth/logout",
    /** Private-alpha gate (owner ruling 2026-08-09, shipped 97dfdb7). Public,
     *  non-disclosing — see `specification/api/ROUTES.md` §Waitlist. */
    waitlistJoin: "/waitlist",
    waitlistResend: "/waitlist/resend",
    me: "/auth/me",
    /**
     * Server-side OAuth start. The browser navigates here; the backend
     * runs the provider handshake and redirects back to /app with an
     * httpOnly session cookie set.
     */
    oauthStart: "/auth/oauth/:provider",
    /** Projects (clients / bodies of work). List/create at the collection,
     *  rename (PATCH) / delete at the item. Runs + memory take a ?projectId filter. */
    projects: "/projects",
    project: "/projects/:id",
    runs: "/runs",
    run: "/runs/:id",
    createRun: "/runs",
    /** Server-Sent Events stream of RunEvent payloads. */
    runStream: "/runs/:id/stream",
    /** Cooperatively cancel an in-flight run. Idempotent; the authoritative
     *  `cancelled` status arrives over the stream. */
    runCancel: "/runs/:id/cancel",
    /** Download one of a run's published artifacts by name (bytes, attachment). */
    runArtifact: "/runs/:id/artifacts/:name",
    /** Thumbs rating (+ optional note) on a delivered run. */
    runFeedback: "/runs/:id/feedback",
    /** Continue a run: spawns the next turn in the same session. */
    runFollowUp: "/runs/:id/followup",
    /** Revise a sent prompt in place: replaces that turn and removes its suffix. */
    runRevision: "/runs/:id/revise",
    /** All retained turns in the run's conversation, oldest first. */
    runThread: "/runs/:id/thread",
    /** Delete a whole conversation (a session and all its turns). */
    session: "/sessions/:id",
    memory: "/memory",
    memoryHydrationPreview: "/memory/hydration-preview",
    memoryEntry: "/memory/:id",
    /** Multipart bulk import of .md/.txt files as wiki entries. */
    memoryUpload: "/memory/upload",
    usage: "/usage",
    modelConfig: "/settings/models",
    /**
     * Billing — mock-mode checkout (no real payment processor live yet).
     * checkout starts a pending upgrade/add-on that the backend confirms
     * server-side; checkoutStatus polls it; portal returns the mock
     * account overview. Never call /billing/mock/confirm from here — it's
     * server/webhook-only.
     */
    checkout: "/billing/checkout",
    checkoutStatus: "/billing/checkouts/:id",
    billingPortal: "/billing/portal",
    /**
     * Filed, not yet built server-side:
     * specification/api/requests/2026-08-02_billing-cancel-downgrade-invoices.md.
     * Frontend is built and live against the mock now (owner: build ahead of
     * the backend, the filed contract is the unblock, not a reason to wait).
     */
    invoices: "/billing/invoices",
    cancelSubscription: "/billing/cancel",
    undoCancelSubscription: "/billing/cancel/undo",
    downgrade: "/billing/downgrade",
  },

  /** Request defaults for the http client. */
  http: {
    /** Send cookies — auth is expected to be httpOnly-cookie based. */
    credentials: "include" as RequestCredentials,
    timeoutMs: 30_000,
  },

  features: {
    /** Billing UI is informational until Stripe is wired. */
    billing: true,
    /** Show the no-signup demo entry on the landing page. */
    demo: true,
  },

  /**
   * Client-side behavior limits. In http mode the backend can
   * override these via the read-only /config endpoint — the backend
   * always remains the enforcing authority either way.
   */
  limits: {
    /** Minimum message length. Low on purpose — the workspace is a
     *  conversation, so a two-character "hi" is a valid message. */
    briefMinChars: 2,
  },
} as const;

export type AppConfig = typeof appConfig;

/**
 * Build a link into the workspace. Relative when the workspace shares the
 * marketing origin (the default), absolute when it lives on its own origin
 * (a subdomain). Use this for every marketing→workspace link so moving the
 * workspace to app.clannon.com is a single env-var change.
 */
export function workspaceUrl(path = "/app"): string {
  return appConfig.appUrl ? `${appConfig.appUrl}${path}` : path;
}
