import type { OAuthProvider } from "@/config/site.config";
import type { PlanId } from "@/config/plans";
import type {
  Credentials,
  LayerModelConfig,
  MemoryEntry,
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

  listRuns(): Promise<RunSummary[]>;
  getRun(id: string): Promise<Run>;
  createRun(brief: string): Promise<{ id: string }>;
  /** Live events for a run. Ends when the run reaches a terminal state. */
  streamRun(id: string, signal: AbortSignal): AsyncGenerator<RunEvent>;

  listMemory(): Promise<MemoryEntry[]>;
  saveMemoryEntry(
    entry: Pick<MemoryEntry, "tier" | "title" | "content"> & { id?: string },
  ): Promise<MemoryEntry>;
  deleteMemoryEntry(id: string): Promise<void>;
  /** Bulk import: each .md/.txt file becomes a wiki entry. */
  uploadMemoryFiles(files: File[]): Promise<MemoryEntry[]>;

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
