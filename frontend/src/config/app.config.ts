/**
 * Clannon frontend configuration — the single file to edit when
 * wiring this UI to a real backend.
 *
 * Everything here can be overridden per-environment via NEXT_PUBLIC_*
 * variables (see .env.example). Flip NEXT_PUBLIC_API_MODE to "http",
 * point NEXT_PUBLIC_API_BASE_URL at the FastAPI host, and the whole
 * app switches from the bundled mock to live endpoints. No component
 * imports an URL or fetch call directly — they only know the client
 * in `src/lib/api`.
 */

export type ApiMode = "mock" | "http";

const env = {
  apiMode: process.env.NEXT_PUBLIC_API_MODE,
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL,
  wsBaseUrl: process.env.NEXT_PUBLIC_WS_BASE_URL,
  appUrl: process.env.NEXT_PUBLIC_APP_URL,
};

export const appConfig = {
  /** "mock" runs the bundled simulator; "http" talks to the real backend. */
  apiMode: (env.apiMode === "http" ? "http" : "mock") as ApiMode,

  /** Base URL of the backend — the Vraksha engine (FastAPI). No trailing slash. */
  apiBaseUrl: env.apiBaseUrl?.replace(/\/$/, "") ?? "http://localhost:8000",

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
    me: "/auth/me",
    /**
     * Server-side OAuth start. The browser navigates here; the backend
     * runs the provider handshake and redirects back to /app with an
     * httpOnly session cookie set.
     */
    oauthStart: "/auth/oauth/:provider",
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
    /** All turns of a run's session, oldest first. */
    runThread: "/runs/:id/thread",
    /** Delete a whole conversation (a session and all its turns). */
    session: "/sessions/:id",
    memory: "/memory",
    memoryEntry: "/memory/:id",
    /** Multipart bulk import of .md/.txt files as wiki entries. */
    memoryUpload: "/memory/upload",
    usage: "/usage",
    modelConfig: "/settings/models",
    /**
     * Billing. checkout returns { url } (Stripe Checkout session) for
     * the browser to redirect to; portal returns { url } (Stripe
     * customer portal). The mock applies plan changes directly.
     */
    checkout: "/billing/checkout",
    billingPortal: "/billing/portal",
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
