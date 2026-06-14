import { appConfig } from "@/config/app.config";
import type { OAuthProvider } from "@/config/site.config";
import type { PlanId } from "@/config/plans";
import type { ClannonClient } from "./client";
import {
  ApiError,
  type Credentials,
  type DecisionLogEntry,
  type LayerModelConfig,
  type MemoryEntry,
  type Run,
  type RunEvent,
  type RemoteConfig,
  type RunSummary,
  type SignupInput,
  type UsageSummary,
  type User,
} from "./types";
import {
  buildRunScript,
  buildSeedUsage,
  SAMPLE_REPORT,
  SEED_MEMORY,
  SEED_MODEL_CONFIG,
  SEED_RUNS,
} from "./mock-data";

const SESSION_KEY = "clannon.mock.session";

const sleep = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(t);
        reject(new DOMException("aborted", "AbortError"));
      },
      { once: true },
    );
  });

let counter = 0;
const nextId = (prefix: string) => `${prefix}_${Date.now().toString(36)}_${++counter}`;

/** Map a picked file to its input modality, mirroring the backend's labels. */
function modalityOf(file: File): string {
  if (file.type.startsWith("image/")) return "image";
  if (file.type.startsWith("audio/")) return "audio";
  if (file.type.startsWith("video/")) return "video";
  if (file.type.includes("pdf")) return "pdf";
  return "text";
}

/**
 * In-browser simulator of the Clannon pipeline. Implements the same
 * interface as HttpClient so the rest of the app cannot tell the
 * difference — which is exactly the point.
 */
export class MockClient implements ClannonClient {
  private runs = new Map<string, Run>(SEED_RUNS.map((r) => [r.id, structuredClone(r)]));
  private memory: MemoryEntry[] = structuredClone(SEED_MEMORY);
  private usage: UsageSummary = buildSeedUsage();
  private models: LayerModelConfig[] = structuredClone(SEED_MODEL_CONFIG);

  /* ---------- remote config (mock echoes the local defaults) ---------- */

  async getRemoteConfig(): Promise<RemoteConfig> {
    await sleep(120);
    return {
      version: "mock",
      features: { ...appConfig.features },
      limits: { ...appConfig.limits },
    };
  }

  /* ---------- auth (mock: any well-formed credentials work) ---------- */

  async login({ email, password }: Credentials): Promise<User> {
    await sleep(650);
    if (!email.includes("@") || password.length < 8) {
      throw new ApiError("Invalid email or password.", 401);
    }
    const user: User = {
      id: "u_demo",
      name: email.split("@")[0].replace(/[._-]/g, " "),
      email,
      plan: "pro",
    };
    this.persistSession(user);
    return user;
  }

  async signup({ name, email, password }: SignupInput): Promise<User> {
    await sleep(800);
    if (password.length < 8) {
      throw new ApiError("Password must be at least 8 characters.", 422);
    }
    const user: User = { id: "u_demo", name, email, plan: "free" };
    this.persistSession(user);
    return user;
  }

  async loginWithProvider(provider: OAuthProvider): Promise<User> {
    // simulate the redirect round-trip
    await sleep(900);
    const user: User = {
      id: "u_demo",
      name: `${provider} user`,
      email: `you@${provider}.example`,
      plan: "pro",
    };
    this.persistSession(user);
    return user;
  }

  async logout(): Promise<void> {
    if (typeof window !== "undefined") window.localStorage.removeItem(SESSION_KEY);
  }

  async me(): Promise<User | null> {
    if (typeof window === "undefined") return null;
    const raw = window.localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as User;
    } catch {
      return null;
    }
  }

  private persistSession(user: User) {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(SESSION_KEY, JSON.stringify(user));
    }
  }

  /* ---------- runs ---------- */

  async listRuns(): Promise<RunSummary[]> {
    await sleep(280);
    return [...this.runs.values()]
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
      .map(({ id, title, status, createdAt, tokensUsed, expertCount, sessionId }) => ({
        id,
        title,
        status,
        createdAt,
        tokensUsed,
        expertCount,
        sessionId,
      }));
  }

  async getRun(id: string): Promise<Run> {
    await sleep(220);
    const run = this.runs.get(id);
    if (!run) throw new ApiError("Run not found.", 404);
    return structuredClone(run);
  }

  async createRun(brief: string, files: File[] = []): Promise<{ id: string }> {
    await sleep(450);
    const trimmed = brief.trim();
    if (trimmed.length < appConfig.limits.briefMinChars) {
      throw new ApiError("Brief is too short — give the pipeline something to work with.", 422);
    }
    const id = nextId("run");
    const title = trimmed.length > 64 ? `${trimmed.slice(0, 61).trimEnd()}…` : trimmed;
    const inputs = files.map((f) => ({
      name: f.name,
      modality: modalityOf(f),
      size: f.size,
    }));
    this.runs.set(id, {
      id,
      title,
      brief: trimmed,
      status: "queued",
      createdAt: new Date().toISOString(),
      tokensUsed: 0,
      expertCount: 0,
      decisionLog: [],
      experts: [],
      sources: [],
      artifacts: [],
      inputs,
      sessionId: id, // a root turn opens its own session
    });
    return { id };
  }

  async downloadArtifact(_runId: string, name: string): Promise<Blob> {
    await sleep(200);
    return new Blob([`mock artifact — ${name}`], { type: "text/plain" });
  }

  async setRunFeedback(
    id: string,
    rating: "up" | "down" | null,
    comment?: string,
  ): Promise<void> {
    await sleep(200);
    const run = this.runs.get(id);
    if (!run) throw new ApiError("Run not found.", 404);
    run.feedbackRating = rating;
    run.feedbackComment = comment?.trim() || null;
  }

  async createFollowUp(id: string, brief: string): Promise<{ id: string }> {
    const parent = this.runs.get(id);
    if (!parent) throw new ApiError("Run not found.", 404);
    const { id: newId } = await this.createRun(brief);
    const child = this.runs.get(newId);
    if (child) {
      child.parentRunId = id;
      // inherit the parent's session so the whole conversation is one thread
      child.sessionId = parent.sessionId ?? parent.id;
    }
    return { id: newId };
  }

  async getRunThread(id: string): Promise<Run[]> {
    await sleep(180);
    const anchor = this.runs.get(id);
    if (!anchor) throw new ApiError("Run not found.", 404);
    const session = anchor.sessionId ?? anchor.id;
    return [...this.runs.values()]
      .filter((r) => (r.sessionId ?? r.id) === session)
      .sort((a, b) => a.createdAt.localeCompare(b.createdAt))
      .map((r) => structuredClone(r));
  }

  async *streamRun(id: string, signal: AbortSignal): AsyncGenerator<RunEvent> {
    const run = this.runs.get(id);
    if (!run) throw new ApiError("Run not found.", 404);
    if (run.status === "delivered" || run.status === "blocked" || run.status === "failed") {
      return; // terminal — page renders from getRun()
    }

    for (const step of buildRunScript()) {
      await sleep(step.delay, signal);
      switch (step.kind) {
        case "status": {
          run.status = step.status!;
          yield { type: "status", status: run.status };
          break;
        }
        case "log": {
          const entry: DecisionLogEntry = {
            id: nextId("log"),
            ts: new Date().toISOString(),
            ...step.log!,
          };
          run.decisionLog.push(entry);
          yield { type: "log", entry };
          break;
        }
        case "expert": {
          const expert = { ...step.expert! };
          const idx = run.experts.findIndex((e) => e.id === expert.id);
          if (idx >= 0) run.experts[idx] = expert;
          else run.experts.push(expert);
          run.expertCount = run.experts.length;
          yield { type: "expert", expert };
          break;
        }
        case "sources": {
          run.sources = step.sources!;
          yield { type: "sources", sources: run.sources };
          break;
        }
        case "usage": {
          run.tokensUsed = step.tokensUsed!;
          yield { type: "usage", tokensUsed: run.tokensUsed };
          break;
        }
      }
    }

    // Output filter cleared — stream the report in word chunks.
    const report = `# ${run.title}\n${SAMPLE_REPORT.split("\n").slice(1).join("\n")}`;
    run.status = "delivered";
    yield { type: "status", status: "delivered" };

    const words = report.split(/(?<=\s)/);
    let assembled = "";
    const CHUNK = 6;
    for (let i = 0; i < words.length; i += CHUNK) {
      await sleep(34, signal);
      const chunk = words.slice(i, i + CHUNK).join("");
      assembled += chunk;
      yield { type: "report_delta", text: chunk };
    }
    run.report = assembled;
    yield { type: "report_done" };

    // post-delivery memory writes, like the real pipeline
    this.memory.unshift({
      id: nextId("m"),
      tier: "episodic",
      title: `Delivered: ${run.title}`,
      content: `${run.experts.length} experts, ${Math.round(run.tokensUsed / 1000)}k tokens, ${run.sources.length} sources.`,
      updatedAt: new Date().toISOString(),
      runId: run.id,
    });
    this.usage.used += run.tokensUsed;
  }

  /* ---------- billing (mock: applies the change directly) ---------- */

  async startCheckout(planId: PlanId): Promise<{ url?: string }> {
    await sleep(1100); // simulated payment round-trip
    const user = await this.me();
    if (!user) throw new ApiError("Sign in to change plans.", 401);
    this.persistSession({ ...user, plan: planId });
    return {};
  }

  async openBillingPortal(): Promise<{ url?: string }> {
    await sleep(400);
    return {};
  }

  /* ---------- memory ---------- */

  async listMemory(): Promise<MemoryEntry[]> {
    await sleep(260);
    return structuredClone(this.memory);
  }

  async saveMemoryEntry(
    entry: Pick<MemoryEntry, "tier" | "title" | "content"> & { id?: string },
  ): Promise<MemoryEntry> {
    await sleep(380);
    if (entry.id) {
      const existing = this.memory.find((m) => m.id === entry.id);
      if (!existing) throw new ApiError("Memory entry not found.", 404);
      existing.title = entry.title;
      existing.content = entry.content;
      existing.updatedAt = new Date().toISOString();
      return structuredClone(existing);
    }
    const created: MemoryEntry = {
      id: nextId("m"),
      tier: entry.tier,
      title: entry.title,
      content: entry.content,
      updatedAt: new Date().toISOString(),
    };
    this.memory.unshift(created);
    return structuredClone(created);
  }

  async uploadMemoryFiles(files: File[]): Promise<MemoryEntry[]> {
    await sleep(500);
    if (files.length === 0) throw new ApiError("No files received.", 422);
    if (files.length > 10) throw new ApiError("At most 10 files per upload.", 422);
    const created: MemoryEntry[] = [];
    for (const file of files) {
      if (!/\.(md|markdown|txt)$/i.test(file.name)) {
        throw new ApiError(`${file.name}: only .md, .markdown, .txt files are accepted.`, 422);
      }
      if (file.size > 512 * 1024) throw new ApiError(`${file.name}: larger than 512 KB.`, 422);
      const content = (await file.text()).trim();
      if (!content) throw new ApiError(`${file.name}: file is empty.`, 422);
      const entry: MemoryEntry = {
        id: nextId("m"),
        tier: "wiki",
        title: file.name.replace(/\.(md|markdown|txt)$/i, "").slice(0, 120) || "Untitled",
        content,
        updatedAt: new Date().toISOString(),
      };
      this.memory.unshift(entry);
      created.push(structuredClone(entry));
    }
    return created;
  }

  async deleteMemoryEntry(id: string): Promise<void> {
    await sleep(300);
    this.memory = this.memory.filter((m) => m.id !== id);
  }

  /* ---------- account ---------- */

  async getUsage(): Promise<UsageSummary> {
    await sleep(240);
    return structuredClone(this.usage);
  }

  async getModelConfig(): Promise<LayerModelConfig[]> {
    await sleep(240);
    return structuredClone(this.models);
  }

  async setModelLayer(layer: string, model: string): Promise<void> {
    await sleep(320);
    // per-expert override: "expert:<key>" targets one expert under "experts"
    if (layer.startsWith("expert:")) {
      const key = layer.slice("expert:".length);
      const expertsCfg = this.models.find((m) => m.layer === "experts");
      const expert = expertsCfg?.experts?.find((e) => e.key === key);
      if (!expertsCfg || !expert) throw new ApiError("Unknown expert.", 404);
      if (!expertsCfg.options.includes(model)) {
        throw new ApiError("Model not available for this layer.", 422);
      }
      expert.model = model;
      return;
    }
    const cfg = this.models.find((m) => m.layer === layer);
    if (!cfg) throw new ApiError("Unknown layer.", 404);
    if (cfg.locked) {
      throw new ApiError("This layer is system-managed and cannot be changed.", 403);
    }
    if (!cfg.options.includes(model)) throw new ApiError("Model not available for this layer.", 422);
    cfg.model = model;
    // experts default cascades to experts without their own override
    if (layer === "experts" && cfg.experts) {
      for (const expert of cfg.experts) expert.model = model;
    }
  }
}
