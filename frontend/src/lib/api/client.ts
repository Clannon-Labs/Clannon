import type { OAuthProvider } from "@/config/site.config";
import type { PlanId } from "@/config/plans";
import type {
  BillingPortalInfo,
  CancelSubscriptionResponse,
  CheckoutRequest,
  CheckoutStatus,
  Credentials,
  DowngradeResponse,
  LayerModelConfig,
  HydrationPreviewEntry,
  InvoicesResponse,
  MemoryEntry,
  Project,
  RemoteConfig,
  Run,
  RunEvent,
  RunSummary,
  SignupInput,
  UsageSummary,
  User,
  WaitlistJoinInput,
} from "./types";

/**
 * The one interface every page talks to. Two implementations:
 * the explicit mock simulator and the default HTTP client. Which one you
 * get is decided by `appConfig.apiMode` — HTTP unless mock is explicitly
 * selected. Change the config, not
 * the components. Get an instance via `getClient()` from `@/lib/api`.
 */
export interface ClannonClient {
  /**
   * Read-only sync channel from the backend. Returns null when the
   * backend doesn't serve /config (yet) — local defaults then apply.
   */
  getRemoteConfig(): Promise<RemoteConfig | null>;

  login(input: Credentials): Promise<User>;
  /** Rejects with a 403 `ApiError` when the waitlist is on and no (valid)
   *  `approvalToken` is present — see `SignupInput`. */
  signup(input: SignupInput): Promise<User>;
  /** Always resolves — join/resend never disclose list membership (see
   *  `specification/api/ROUTES.md` §Waitlist), so there is nothing for the
   *  UI to branch on beyond "it didn't throw" vs. a rate-limit 429. */
  joinWaitlist(input: WaitlistJoinInput): Promise<void>;
  resendWaitlistVerification(email: string): Promise<void>;
  /**
   * OAuth sign-in. The http client navigates the browser to the
   * backend's OAuth start route (the returned promise never settles
   * because the page unloads); the mock resolves a simulated user.
   */
  loginWithProvider(provider: OAuthProvider): Promise<User>;
  logout(): Promise<void>;
  me(): Promise<User | null>;

  /** The user's projects (clients / bodies of work), newest activity first. */
  listProjects(): Promise<Project[]>;
  /** Create a project. `seedFacts` (optional markdown) seeds a first wiki entry
   *  in it — the "tell Clannon about this client" onboarding step. */
  createProject(input: { name: string; seedFacts?: string }): Promise<Project>;
  renameProject(id: string, name: string): Promise<Project>;
  /** Delete a project AND cascade its runs + memory. Idempotent. */
  deleteProject(id: string): Promise<void>;

  /** Runs, optionally scoped to one project (omit for all of the user's runs). */
  listRuns(projectId?: string): Promise<RunSummary[]>;
  getRun(id: string): Promise<Run>;
  /** Start a run. Optional input files + per-session model overrides ride along as
   *  multipart. `models` is a sparse { role: modelId } applied to THIS run only.
   *  `projectId` tags the run to a project (omit for the user's default scope). */
  createRun(
    brief: string,
    files?: File[],
    models?: Record<string, string>,
    projectId?: string,
  ): Promise<{ id: string }>;
  /** Download one of a run's published artifacts as a Blob (auth via cookie). */
  downloadArtifact(runId: string, name: string): Promise<Blob>;
  /** Live events for a run. Ends when the run reaches a terminal state. */
  streamRun(id: string, signal: AbortSignal): AsyncGenerator<RunEvent>;
  /** Request cooperative cancellation of an in-flight run. Idempotent — a no-op
   *  on an already-terminal run. The authoritative `cancelled` arrives over the
   *  stream, so this resolves without returning the new state. */
  cancelRun(id: string): Promise<void>;
  /** Attach a thumbs rating (+ optional note) to a delivered run. */
  setRunFeedback(
    id: string,
    rating: "up" | "down" | null,
    comment?: string,
  ): Promise<void>;
  /** Continue a run: a new turn in the same session, threading prior context.
   *  Optional input files + per-session model overrides ride along, same as createRun. */
  createFollowUp(
    id: string,
    brief: string,
    files?: File[],
    models?: Record<string, string>,
  ): Promise<{ id: string }>;
  /** Replace an edited sent prompt in its existing session. The old turn and
   *  every descendant are removed; saved memory remains separate and intact. */
  reviseRun(
    id: string,
    brief: string,
    files?: File[],
    models?: Record<string, string>,
  ): Promise<{ id: string }>;
  /** Every retained turn in this run's conversation, oldest first. */
  getRunThread(id: string): Promise<Run[]>;
  /** Delete a whole conversation — the session and every turn in it. */
  deleteSession(sessionId: string): Promise<void>;

  /** Memory, optionally scoped to one project (omit for all of the user's memory). */
  listMemory(projectId?: string): Promise<MemoryEntry[]>;

  /** Dry-run of what the Manager would hydrate for a draft brief — the real
   *  ranking behind the hydration panel's "in reach" chip. Render-only
   *  (learned-tier ids are synthetic); resolves [] on any fault, never throws. */
  hydrationPreview(brief: string, projectId?: string): Promise<HydrationPreviewEntry[]>;
  /** Save a wiki entry; `projectId` scopes a NEW entry to a project (edits keep
   *  their existing scope). */
  saveMemoryEntry(
    entry: Pick<MemoryEntry, "tier" | "title" | "content"> & { id?: string },
    projectId?: string,
  ): Promise<MemoryEntry>;
  deleteMemoryEntry(id: string): Promise<void>;
  /** Bulk import: each .md/.txt file becomes a wiki entry (scoped to `projectId`). */
  uploadMemoryFiles(files: File[], projectId?: string): Promise<MemoryEntry[]>;

  getUsage(): Promise<UsageSummary>;
  getModelConfig(): Promise<LayerModelConfig[]>;
  setModelLayer(layer: string, model: string): Promise<void>;

  /**
   * Start a checkout — "upgrade" (move to a higher plan) or "add_on" (buy
   * extra credits on the current plan). There is no real payment processor
   * live yet (private alpha): this returns a PENDING checkout that the
   * backend confirms server-side (webhook/operator, never the browser —
   * `POST /billing/mock/confirm` must never be called from here). Poll
   * `getCheckoutStatus` or refetch usage/plan to observe confirmation.
   */
  startCheckout(input: CheckoutRequest): Promise<CheckoutStatus>;
  /** Poll a checkout's status after starting it. */
  getCheckoutStatus(id: string): Promise<CheckoutStatus>;
  /** Mock-mode billing overview — no real Stripe portal yet. */
  openBillingPortal(): Promise<BillingPortalInfo>;
  /** The account's real billing history — distinct from `getCheckoutStatus`,
   *  which is a single pending checkout's status. */
  getInvoices(): Promise<InvoicesResponse>;
  /** Schedule the account to drop to Free at the current period's end.
   *  Access continues through `cancelEffectiveAt` — this product bills fixed
   *  monthly budgets, not a metered subscription, so cancel never revokes
   *  access immediately. Idempotent on an already-scheduled account. */
  cancelSubscription(reason?: string): Promise<CancelSubscriptionResponse>;
  /** Reverse a scheduled cancellation. No-op if the account isn't scheduled. */
  undoCancelSubscription(): Promise<void>;
  /** Move to a lower plan, effective immediately. Blocked (409) if the
   *  account's current-period usage already exceeds the target plan's
   *  budget — the caller can't silently go over budget on downgrade. */
  downgradePlan(targetPlanId: PlanId): Promise<DowngradeResponse>;
}
