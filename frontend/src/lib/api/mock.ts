import { appConfig } from "@/config/app.config";
import type { OAuthProvider } from "@/config/site.config";
import { planById, type PlanId } from "@/config/plans";
import type { ClannonClient } from "./client";
import {
  ApiError,
  type Credentials,
  type DecisionLogEntry,
  type LayerModelConfig,
  type MemoryEntry,
  type Project,
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
  SEED_PROJECTS,
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

// Palette keys a new project cycles through (the UI maps these to a dot color).
const PROJECT_COLORS = ["moss", "clay", "indigo", "amber", "rose", "slate"];

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
  private projects: Project[] = structuredClone(SEED_PROJECTS);
  private runs = new Map<string, Run>(SEED_RUNS.map((r) => [r.id, structuredClone(r)]));
  private memory: MemoryEntry[] = structuredClone(SEED_MEMORY);
  private usage: UsageSummary = buildSeedUsage();
  private models: LayerModelConfig[] = structuredClone(SEED_MODEL_CONFIG);
  /** Run ids the user asked to stop — the live stream notices and unwinds. */
  private cancelRequested = new Set<string>();

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

  /* ---------- projects (clients / bodies of work) ---------- */

  async listProjects(): Promise<Project[]> {
    await sleep(160);
    // newest activity first; mirror the proposed server ordering
    return structuredClone(this.projects).sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  }

  async createProject(input: { name: string; seedFacts?: string }): Promise<Project> {
    await sleep(360);
    const name = input.name.trim();
    if (!name) throw new ApiError("A project needs a name.", 422);
    const project: Project = {
      id: nextId("proj"),
      name,
      createdAt: new Date().toISOString(),
      color: PROJECT_COLORS[this.projects.length % PROJECT_COLORS.length],
    };
    this.projects.push(project);
    // the "tell Clannon about this client" seed → a first wiki entry in the project
    const facts = input.seedFacts?.trim();
    if (facts) {
      this.memory.unshift({
        id: nextId("m"),
        tier: "wiki",
        title: `Client: ${name} — context`,
        content: facts,
        updatedAt: new Date().toISOString(),
        projectId: project.id,
      });
    }
    return structuredClone(project);
  }

  async renameProject(id: string, name: string): Promise<Project> {
    await sleep(240);
    const project = this.projects.find((p) => p.id === id);
    if (!project) throw new ApiError("Project not found.", 404);
    const trimmed = name.trim();
    if (!trimmed) throw new ApiError("A project needs a name.", 422);
    project.name = trimmed;
    return structuredClone(project);
  }

  async deleteProject(id: string): Promise<void> {
    await sleep(280);
    this.projects = this.projects.filter((p) => p.id !== id);
    // cascade: drop the project's runs and memory (same as delete-session)
    for (const [runId, run] of this.runs) {
      if (run.projectId === id) this.runs.delete(runId);
    }
    this.memory = this.memory.filter((m) => m.projectId !== id);
  }

  /* ---------- runs ---------- */

  async listRuns(projectId?: string): Promise<RunSummary[]> {
    await sleep(280);
    return [...this.runs.values()]
      .filter((r) => !projectId || r.projectId === projectId)
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
      .map(({ id, title, status, createdAt, tokensUsed, expertCount, sessionId, projectId: pid }) => ({
        id,
        title,
        status,
        createdAt,
        tokensUsed,
        expertCount,
        sessionId,
        projectId: pid,
      }));
  }

  async getRun(id: string): Promise<Run> {
    await sleep(220);
    const run = this.runs.get(id);
    if (!run) throw new ApiError("Run not found.", 404);
    return structuredClone(run);
  }

  // Note: the http client also passes per-session `models`, but the mock has no
  // Run field to reflect them, so it accepts only the args it can simulate.
  async createRun(
    brief: string,
    files: File[] = [],
    _models?: Record<string, string>,
    projectId?: string,
  ): Promise<{ id: string }> {
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
      projectId,
    });
    return { id };
  }

  async downloadArtifact(_runId: string, name: string): Promise<Blob> {
    await sleep(200);
    // return content that matches the file type so inline preview is realistic
    if (/\.(md|markdown)$/i.test(name)) {
      return new Blob(
        [
          `# ${name.replace(/\.(md|markdown)$/i, "")}\n\n` +
            "This is a **preview** of a delivered markdown artifact, rendered inline — " +
            "no download needed.\n\n## Highlights\n\n- Every figure is source-checked\n" +
            "- Tables and headings render as the report does\n- Download stays one tap away\n\n" +
            "> Generated by the Clannon pipeline.\n",
        ],
        { type: "text/markdown" },
      );
    }
    if (/\.csv$/i.test(name)) {
      return new Blob(
        ["metric,value\nmarket size 2026,£3.4B\nDTC price band,£22–£38\nlead time,6–9 weeks\n"],
        { type: "text/csv" },
      );
    }
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

  async createFollowUp(id: string, brief: string, files: File[] = []): Promise<{ id: string }> {
    const parent = this.runs.get(id);
    if (!parent) throw new ApiError("Run not found.", 404);
    const { id: newId } = await this.createRun(brief, files);
    const child = this.runs.get(newId);
    if (child) {
      child.parentRunId = id;
      // inherit the parent's session so the whole conversation is one thread
      child.sessionId = parent.sessionId ?? parent.id;
      // and the parent's project — a follow-up stays in the same client space
      child.projectId = parent.projectId;
    }
    return { id: newId };
  }

  async cancelRun(id: string): Promise<void> {
    await sleep(150);
    const run = this.runs.get(id);
    if (!run) throw new ApiError("Run not found.", 404);
    // idempotent: cancelling an already-terminal run is a no-op
    if (["delivered", "blocked", "failed", "cancelled"].includes(run.status)) return;
    this.cancelRequested.add(id); // the live stream picks this up and unwinds
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

  async deleteSession(sessionId: string): Promise<void> {
    await sleep(220);
    for (const [id, run] of this.runs) {
      if ((run.sessionId ?? run.id) === sessionId) this.runs.delete(id);
    }
  }

  async *streamRun(id: string, signal: AbortSignal): AsyncGenerator<RunEvent> {
    const run = this.runs.get(id);
    if (!run) throw new ApiError("Run not found.", 404);
    if (["delivered", "blocked", "failed", "cancelled"].includes(run.status)) {
      return; // terminal — page renders from getRun()
    }

    // user pressed Stop — settle the run as cancelled and end the stream
    const stopIfCancelled = (): RunEvent | null => {
      if (!this.cancelRequested.has(id)) return null;
      this.cancelRequested.delete(id);
      run.status = "cancelled";
      return { type: "status", status: "cancelled" };
    };

    for (const step of buildRunScript()) {
      await sleep(step.delay, signal);
      const stopped = stopIfCancelled();
      if (stopped) {
        yield stopped;
        return;
      }
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
        case "message": {
          // the orchestrator talking — stream it in chunks for a live-typing feel
          const words = step.message!.split(/(?<=\s)/);
          const CHUNK_W = 4;
          for (let i = 0; i < words.length; i += CHUNK_W) {
            const chunk = words.slice(i, i + CHUNK_W).join("");
            run.message = (run.message ?? "") + chunk;
            yield { type: "message_delta", text: chunk };
            await sleep(55, signal);
            const stopMid = stopIfCancelled();
            if (stopMid) {
              yield stopMid;
              return;
            }
          }
          yield { type: "message_done" };
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
      const stopped = stopIfCancelled();
      if (stopped) {
        yield stopped;
        return;
      }
      const chunk = words.slice(i, i + CHUNK).join("");
      assembled += chunk;
      yield { type: "report_delta", text: chunk };
    }
    run.report = assembled;
    yield { type: "report_done" };

    // post-delivery memory writes, like the real pipeline (scoped to the project)
    this.memory.unshift({
      id: nextId("m"),
      tier: "episodic",
      title: `Delivered: ${run.title}`,
      content: `${run.experts.length} experts, ${Math.round(run.tokensUsed / 1000)}k tokens, ${run.sources.length} sources.`,
      updatedAt: new Date().toISOString(),
      runId: run.id,
      projectId: run.projectId,
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

  async listMemory(projectId?: string): Promise<MemoryEntry[]> {
    await sleep(260);
    return structuredClone(this.memory.filter((m) => !projectId || m.projectId === projectId));
  }

  async saveMemoryEntry(
    entry: Pick<MemoryEntry, "tier" | "title" | "content"> & { id?: string },
    projectId?: string,
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
      projectId,
    };
    this.memory.unshift(created);
    return structuredClone(created);
  }

  async uploadMemoryFiles(files: File[], projectId?: string): Promise<MemoryEntry[]> {
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
        projectId,
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
    // computed live: spend is the sum of real run tokens, budget is the user's
    // plan — not a static seed. Mirrors how the backend meters per call.
    const user = await this.me();
    const plan = planById(user?.plan ?? "free");
    const runs = [...this.runs.values()];
    const used = runs.reduce((sum, r) => sum + (r.tokensUsed ?? 0), 0);

    const days = 14;
    const byDay = Array.from({ length: days }, (_, i) => {
      const date = new Date(Date.now() - (days - 1 - i) * 86_400_000)
        .toISOString()
        .slice(0, 10);
      const tokens = runs
        .filter((r) => r.createdAt.slice(0, 10) === date)
        .reduce((sum, r) => sum + (r.tokensUsed ?? 0), 0);
      return { date, tokens };
    });

    return {
      periodStart: byDay[0].date,
      periodEnd: new Date(new Date(byDay[0].date).getTime() + 30 * 86_400_000)
        .toISOString()
        .slice(0, 10),
      budget: plan.tokenBudget,
      used,
      byDay,
    };
  }

  async getModelConfig(): Promise<LayerModelConfig[]> {
    await sleep(240);
    return structuredClone(this.models);
  }

  async setModelLayer(layer: string, model: string): Promise<void> {
    await sleep(320);
    const cfg = this.models.find((m) => m.layer === layer);
    if (!cfg) throw new ApiError("Unknown role.", 404);
    if (cfg.locked) {
      throw new ApiError("This role is system-managed and cannot be changed.", 403);
    }
    if (!cfg.options.includes(model)) throw new ApiError("Model not available for this role.", 422);
    cfg.model = model;
  }
}
