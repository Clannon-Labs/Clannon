/**
 * Frontend mirrors of the Flow pipeline contracts. Field names follow
 * the backend's structured schemas so the http client can pass JSON
 * through without remapping.
 */

import type { MemoryTier, Plan, PlanId } from "@/config/plans";

/* ---------- pipeline / runs ---------- */

export type RunStatus =
  | "queued"
  | "sanitizing"
  | "verifying"
  | "orchestrating"
  | "filtering"
  | "delivered"
  | "blocked"
  | "failed"
  /** User stopped the run before it finished (POST /runs/:id/cancel). Terminal,
   *  but not a failure — partial work is kept, the conversation can continue. */
  | "cancelled";

export type DecisionKind =
  | "hydration"
  | "route"
  | "expert_spawn"
  | "tool_call"
  | "observation"
  | "answer"
  | "warning"
  | "error";

export interface DecisionLogEntry {
  id: string;
  ts: string;
  kind: DecisionKind;
  title: string;
  detail?: string;
  /** e.g. { entropy: "0.82", domains: "market, regulatory" } */
  meta?: Record<string, string>;
}

export type ExpertStatus = "spawned" | "working" | "summarizing" | "done" | "failed";

export interface ExpertState {
  id: string;
  name: string;
  domain: string;
  status: ExpertStatus;
  /** Brief structured summary — full findings go to the output pipeline. */
  summary?: string;
  toolCalls: number;
}

export interface Source {
  id: string;
  title: string;
  url: string;
  domain: string;
}

/**
 * A file the run produced for download (output side), fetched via
 * GET /runs/:id/artifacts/:name. The backend sends snake_case `run_id`
 * for this shape (unlike the camelCase run/user shapes) — keep it as-is.
 */
export interface Artifact {
  id: string;
  run_id: string;
  name: string;
  mime: string;
  size: number;
}

/**
 * A file attached to a run at creation (input side), after the boundary
 * malware scan. `modality` is free-form so new kinds (image/audio/video)
 * slot in without a type change — today it's "text" | "pdf".
 */
export interface InputFileMeta {
  name: string;
  modality: string;
  size: number;
}

export interface RunSummary {
  id: string;
  title: string;
  status: RunStatus;
  createdAt: string;
  tokensUsed: number;
  expertCount: number;
  /** The session this turn belongs to — used to group turns into one thread. */
  sessionId?: string;
  /** The project (client/body of work) this run belongs to. */
  projectId?: string;
}

export interface Run extends RunSummary {
  brief: string;
  decisionLog: DecisionLogEntry[];
  experts: ExpertState[];
  /**
   * The agent talking to you — conversational framing, caveats, a clarifying
   * question. Free commentary (NOT output-filtered), kept separate from the
   * deliverable. A turn may have a message, a report, both, or neither.
   */
  message?: string;
  /** Markdown deliverable. The grounded, output-filtered result. */
  report?: string;
  sources: Source[];
  /** Files this run delivered for download. Empty until an expert publishes one. */
  artifacts: Artifact[];
  /** Files attached to this run at creation. Empty for a typed-only brief. */
  inputs: InputFileMeta[];
  /** User's thumbs rating on the delivered report, if given. */
  feedbackRating?: "up" | "down" | null;
  feedbackComment?: string | null;
  /** Set when this run is a follow-up; links back to the run it continues. */
  parentRunId?: string | null;
  /** The session this turn belongs to. Root turns own their session; follow-ups
   *  inherit the parent's, so a whole conversation shares one sessionId. */
  sessionId?: string;
  /** Which gate blocked the run, when status is "blocked":
   *  "sanitize" | "verify" (input-side — nothing reached the models) |
   *  "filter" (output-side — a draft was produced then held back) | "security". */
  blockStage?: "sanitize" | "verify" | "filter" | "security" | null;
  /** The output filter's verdict on this run. Not yet surfaced in the UI. */
  verificationState?: VerificationState | null;
  /** Did the loop finish the work it planned, independent of `status` and
   *  `verificationState`? A `delivered` run is routinely `complete: "grounded"`
   *  and `completionState: "partial"` at once — it really was delivered, the
   *  answer really is grounded, and it really didn't finish everything planned.
   *  See INTEGRATION_CONTRACT.md — the three axes are never collapsed into one. */
  completionState?: CompletionState;
  /** Why the loop stopped short, when `completionState` is `"partial"`. `null`
   *  when the cause wasn't classified, or the run is fully `"complete"`. */
  completionReason?: CompletionReason;
}

/** The output filter's verdict on a run's delivered/blocked draft. `null` only
 *  when the filter never ran (an earlier gate blocked first). "not_applicable"
 *  is a non-research turn that never claimed anything checkable — not a failure. */
export type VerificationState = "grounded" | "partial" | "ungrounded" | "not_applicable";

/** Whether the loop finished everything it planned before stopping. */
export type CompletionState = "complete" | "partial";

/** Cause of a partial completion — why the loop stopped short. */
export type CompletionReason = "timeout" | "rate_limit" | "error" | null;

/** Events emitted on a live run stream (SSE `data:` payloads). */
export type RunEvent =
  | { type: "status"; status: RunStatus }
  | { type: "log"; entry: DecisionLogEntry }
  | { type: "expert"; expert: ExpertState }
  | { type: "sources"; sources: Source[] }
  /** The orchestrator talking, live — can stream while experts work. Distinct
   *  from `report_delta` (the deliverable) and `log` (structured ticks). */
  | { type: "message_delta"; text: string }
  | { type: "message_done" }
  | { type: "report_delta"; text: string }
  | { type: "report_done" }
  | { type: "usage"; tokensUsed: number }
  /** Emitted once per run, right before the terminal `status` event. Typed but
   *  not yet surfaced in the UI — backlogged, see proposals/archive/to-frontend/
   *  2026-07-26_cb5-verification-seal-available.md. */
  | { type: "verification"; state: VerificationState };

/* ---------- memory ---------- */

export interface MemoryEntry {
  id: string;
  tier: MemoryTier;
  title: string;
  content: string;
  updatedAt: string;
  /** semantic tier */
  confidence?: number;
  source?: string;
  /** Manager-owned persistence provenance. */
  savedBy?: "user" | "memory_curator" | "system" | "orchestrator" | "unspecified";
  rationale?: string;
  kind?: "fact" | "assumption" | "decision" | "unspecified";
  sessionId?: string;
  traceId?: string;
  participants?: string[];
  /** episodic tier */
  runId?: string;
  /** The project (client/body of work) this memory belongs to. */
  projectId?: string;
}

/**
 * One hydration-preview hit — a dry-run of what the Manager would hydrate for
 * a draft brief. Render-only; unsaved hits may carry synthetic `preview_<n>`
 * ids (never build mutations off those) and may lack a timestamp.
 */
export interface HydrationPreviewEntry extends Omit<MemoryEntry, "updatedAt"> {
  updatedAt: string | null;
  /** Relevance from the real ranking, clamped 0..1, best-first. */
  score: number;
}

/**
 * A project: a client or a body of work. Sessions (runs) and memory are scoped
 * to one. "Current project" is client-side state — every scoped request carries
 * the projectId. See the Projects proposal in conversation/proposal.md.
 */
export interface Project {
  id: string;
  name: string;
  createdAt: string;
  /** A palette key for the project's dot/accent in the UI (not a raw color). */
  color?: string;
}

/* ---------- account ---------- */

export interface User {
  id: string;
  name: string;
  email: string;
  plan: PlanId;
}

export interface UsageDay {
  date: string;
  tokens: number;
}

export interface UsageSummary {
  periodStart: string;
  /** The reset boundary — EXCLUSIVE. Usage resets AT this instant, not on
   *  this calendar day; display it as "resets <periodEnd>", never as the
   *  last day still counted. See `periodEndExclusive`. */
  periodEnd: string;
  periodEndExclusive: true;
  /** The plan's own allowance, before any add-on credits. */
  baseBudget: number;
  /** Confirmed add-on credits purchased this period (0 if none). */
  additionalCredits: number;
  /** baseBudget + additionalCredits — the number every "X left" display
   *  should use, not baseBudget alone. */
  budget: number;
  used: number;
  /** Diagnostic cost context — priced differently from `used` and NEVER
   *  added into it (backend keeps them deliberately separate). */
  cacheReadTokens: number;
  cacheWriteTokens: number;
  byDay: UsageDay[];
  /** How long recent runs actually took, this period. `p50`/`p95` are
   *  `null` on an empty sample — never `0`, an empty sample is not a fast
   *  one. Absent entirely on accounts old enough to predate this field. */
  latency?: {
    inPeriod: number;
    timeToFirstMessageMs: UsageLatencySample;
    totalDurationMs: UsageLatencySample;
  };
}

export interface UsageLatencySample {
  sampleSize: number;
  excluded: number;
  p50: number | null;
  p95: number | null;
}

/**
 * A selectable pipeline role. Known roles are listed for autocomplete, but the
 * UI renders whatever the backend sends — a new role appears with no type change.
 */
export type PipelineLayer =
  | "orchestrator"
  | "research"
  | "planner"
  | "code"
  | "media_expert"
  | "verifier"
  | "filter"
  | (string & {});

export interface LayerModelConfig {
  /** The role string, e.g. "orchestrator" | "media_expert". */
  layer: PipelineLayer;
  label: string;
  description: string;
  /** The user's current choice for this role (their default, if unset). */
  model: string;
  /** Models selectable for this role. media_expert carries a vision-only list. */
  options: string[];
  /**
   * System-managed role (verifier, output filter): the model is part of the
   * security posture and cannot be changed. The backend rejects writes with 403;
   * the UI renders it read-only.
   */
  locked?: boolean;
  /** The best-for-task default the backend uses when the user hasn't chosen. */
  default?: string;
  /**
   * The registered experts this role drives, registry-derived by the backend
   * (`GET /settings/models`) — it auto-updates when a backend expert is added or
   * renamed, so the UI can explain the role→capability mapping with no frontend
   * change. Informational; absent for roles that drive none (orchestrator, the
   * locked gates). `label` is display-ready; `key` is the stable registry id.
   */
  experts?: { key: string; label: string }[];
}

/* ---------- remote config (backend → frontend, read-only) ---------- */

/**
 * Served by the backend's public, unauthenticated, GET-only /config
 * endpoint. Whatever it includes overrides the frontend's local
 * defaults — plans, feature flags, limits — so backend and frontend
 * never drift. The frontend has no write path to any of this; the
 * backend stays the enforcing authority for every limit regardless
 * of what the UI shows.
 */
export interface RemoteConfig {
  /** Backend version/build tag, surfaced for support and debugging. */
  version?: string;
  /** Overrides src/config/plans.ts when present. */
  plans?: Plan[];
  /** Overrides appConfig.features when present. */
  features?: { demo?: boolean; billing?: boolean };
  /** Overrides appConfig.limits when present. */
  limits?: { briefMinChars?: number };
}

/* ---------- auth ---------- */

export interface Credentials {
  email: string;
  password: string;
}

export interface SignupInput extends Credentials {
  name: string;
}

/** The concrete "what can I do about it" options a 402 offers — rendered as
 *  real action buttons per the backend contract ("do not collapse this to
 *  generic failure"), not just read off `message` as plain text. */
export interface ApiErrorAction {
  kind: "add_on" | "upgrade";
  endpoint: "/billing/checkout";
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
    /** Present on a 402 token_budget_exhausted response — the exact
     *  numbers and reset date so the UI can say something concrete instead
     *  of re-deriving them from a stale usage fetch. */
    public used?: number,
    public budget?: number,
    public periodEnd?: string,
    public actions?: ApiErrorAction[],
    public periodEndExclusive?: true,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/* ---------- billing / checkout ---------- */

/** "upgrade" moves to a higher plan; "add_on" buys extra credits on the
 *  current plan. There is no downgrade kind in this contract — see the
 *  frontend↔backend proposal thread for why (flagged, not guessed). */
export type CheckoutKind = "upgrade" | "add_on";

export type CheckoutRequest =
  | { kind: "upgrade"; planId: PlanId }
  | { kind: "add_on"; creditAmount: number };

/** Mock/real checkout shape returned on creation and status polling. */
export interface CheckoutStatus {
  id: string;
  kind: CheckoutKind;
  status: "pending" | "confirmed" | "failed";
  planId: PlanId | null;
  creditAmount: number | null;
  createdAt: string;
  settledAt: string | null;
}

/** Whether the account is scheduled to drop to Free at the current period's
 *  end. This product bills fixed monthly budgets, not a metered
 *  subscription, so "cancel" means "don't renew," never "revoke access
 *  now" — access continues through `cancelEffectiveAt`. */
export interface SubscriptionStatus {
  status: "active" | "cancel_scheduled";
  /** ISO, null when `status` is "active". */
  cancelEffectiveAt: string | null;
}

/** POST /billing/portal's mock-mode response. There is no real Stripe
 *  portal yet (private alpha) — this describes the mock's own state
 *  instead of a redirect URL. */
export interface BillingPortalInfo {
  mode: "mock";
  planId: PlanId;
  maxAddOnCredits: number;
  checkouts: CheckoutStatus[];
  subscription: SubscriptionStatus;
}

/** One line item a user can point to and say "that's what I was charged."
 *  Distinct from `CheckoutStatus`, which is a checkout *event* log — this is
 *  the account's billing history proper. */
export interface Invoice {
  id: string;
  issuedAt: string;
  amountCents: number;
  currency: string;
  status: "paid" | "open" | "void" | "refunded";
  description: string;
}

export interface InvoicesResponse {
  invoices: Invoice[];
}

export type CancelSubscriptionResponse = SubscriptionStatus;

export type DowngradeResponse = {
  status: "applied";
  effectiveAt: string;
  newPlanId: PlanId;
};
