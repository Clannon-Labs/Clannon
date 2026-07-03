import type { OAuthProvider } from "@/config/site.config";
import type { PlanId } from "@/config/plans";
import type {
  Credentials,
  LayerModelConfig,
  HydrationPreviewEntry,
  MemoryEntry,
  Project,
  RemoteConfig,
  Run,
  RunEvent,
  RunSummary,
  SignupInput,
  UsageSummary,
  User,
} from "./types";

/**
 * The one interface every page talks to. Two implementations:
 * the mock simulator (default) and the http client. Which one you
 * get is decided by `appConfig.apiMode` — change the config, not
 * the components. Get an instance via `getClient()` from `@/lib/api`.
 */
export interface ClannonClient {
  /**
   * Read-only sync channel from the backend. Returns null when the
   * backend doesn't serve /config (yet) — local defaults then apply.
   */
  getRemoteConfig(): Promise<RemoteConfig | null>;

  login(input: Credentials): Promise<User>;
  signup(input: SignupInput): Promise<User>;
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
  /** Every turn of this run's session, oldest first — the conversation thread. */
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
   * Start a plan change. Real backend returns a Stripe Checkout URL
   * for the browser to redirect to; the mock applies the change
   * directly and returns no URL.
   */
  startCheckout(planId: PlanId): Promise<{ url?: string }>;
  /** Stripe customer portal (manage/cancel). Same url contract. */
  openBillingPortal(): Promise<{ url?: string }>;
}
