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
  | "failed";

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

export interface RunSummary {
  id: string;
  title: string;
  status: RunStatus;
  createdAt: string;
  tokensUsed: number;
  expertCount: number;
}

export interface Run extends RunSummary {
  brief: string;
  decisionLog: DecisionLogEntry[];
  experts: ExpertState[];
  /** Markdown. Only present once the output filter has cleared it. */
  report?: string;
  sources: Source[];
}

/** Events emitted on a live run stream (SSE `data:` payloads). */
export type RunEvent =
  | { type: "status"; status: RunStatus }
  | { type: "log"; entry: DecisionLogEntry }
  | { type: "expert"; expert: ExpertState }
  | { type: "sources"; sources: Source[] }
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

export type PipelineLayer = "verifier" | "orchestrator" | "experts" | "filter";

export interface LayerModelConfig {
  layer: PipelineLayer;
  label: string;
  description: string;
  model: string;
  options: string[];
  /**
   * System-managed layer (verifier, output filter): the model is part
   * of the security posture and cannot be changed by users. The
   * backend rejects writes with 403; the UI renders it read-only.
   */
  locked?: boolean;
  /**
   * Present on the "experts" layer: individually overridable experts.
   * Write one via setModelLayer("expert:<key>", model); unset experts
   * follow the layer default.
   */
  experts?: { key: string; label: string; model: string }[];
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
