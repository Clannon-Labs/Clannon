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
}

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
  | { type: "usage"; tokensUsed: number };

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
  /** episodic tier */
  runId?: string;
  /** The project (client/body of work) this memory belongs to. */
  projectId?: string;
}

/**
 * One hydration-preview hit — a dry-run of what the Manager would hydrate for
 * a draft brief. Render-only: learned-tier hits carry synthetic `preview_<n>`
 * ids (never build links or mutations off them) and may lack a timestamp.
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
  periodEnd: string;
  budget: number;
  used: number;
  byDay: UsageDay[];
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

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
