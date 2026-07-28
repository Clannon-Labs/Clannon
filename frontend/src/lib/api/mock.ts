import { appConfig } from "@/config/app.config";
import { DEMO_BRIEFS } from "@/config/demo.config";
import type { OAuthProvider } from "@/config/site.config";
import { planById, type PlanId } from "@/config/plans";
import type { ClannonClient } from "./client";
import {
  ApiError,
  type Credentials,
  type DecisionLogEntry,
  type LayerModelConfig,
  type HydrationPreviewEntry,
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
// Whether the current session is a freshly-signed-up account that must stay
// genuinely empty (see MockClient constructor). Without this, a page reload
// re-runs the class field initializers below and silently re-seeds a demo
// stranger's "Meridian Skincare" project/data onto what the user was just
// promised was a blank account — the empty-signup fix only held until the
// next navigation. Persisted so it survives exactly the reload that broke it.
const EMPTY_ACCOUNT_KEY = "clannon.mock.emptyAccount";

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

/** A genuinely empty 14-day usage window for a freshly-signed-up account —
 *  no fabricated history, matching MockClient's empty-account state. */
function emptyUsage(): UsageSummary {
  const today = new Date();
  return {
    periodStart: today.toISOString().slice(0, 10),
    periodEnd: new Date(today.getTime() + 30 * 86_400_000).toISOString().slice(0, 10),
    budget: planById("free").tokenBudget,
    used: 0,
    byDay: Array.from({ length: 14 }, (_, i) => ({
      date: new Date(today.getTime() - (13 - i) * 86_400_000).toISOString().slice(0, 10),
      tokens: 0,
    })),
  };
}

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
  private projects: Project[];
  private runs: Map<string, Run>;
  private memory: MemoryEntry[];
  private usage: UsageSummary;
  private models: LayerModelConfig[] = structuredClone(SEED_MODEL_CONFIG);
  /** Run ids the user asked to stop — the live stream notices and unwinds. */
  private cancelRequested = new Set<string>();

  constructor() {
    // A brand-new instance is constructed on every full page load (this is a
    // client-side singleton, not a server) — so whether to seed demo depth
    // has to be decided from persisted state, not just field defaults.
    const empty =
      typeof window !== "undefined" &&
      window.localStorage.getItem(EMPTY_ACCOUNT_KEY) === "1";
    this.projects = [];
    this.runs = new Map();
    this.memory = [];
    this.usage = emptyUsage();
    if (empty) this.clearToEmptyAccount();
    else this.seedDemoData();
  }

  /** Returning-user story: full seeded depth. Used on construction for a
   *  browser with no empty-account flag, and again in login()/
   *  loginWithProvider() — flipping the persisted flag alone only takes
   *  effect on the *next* load; the already-constructed instance needs its
   *  data populated too, or a login right after a signup stays empty. */
  private seedDemoData() {
    this.projects = structuredClone(SEED_PROJECTS);
    this.runs = new Map(SEED_RUNS.map((r) => [r.id, structuredClone(r)]));
    this.memory = structuredClone(SEED_MEMORY);
    this.usage = buildSeedUsage();
  }

  /** First-user story: nothing yet. Mirrors seedDemoData() for the empty case
   *  so signup() (and a reload with the flag already set) reach the same
   *  truthful-empty state through one path. */
  private clearToEmptyAccount() {
    this.projects = [];
    this.runs.clear();
    this.memory = [];
    this.usage = emptyUsage();
  }

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
    // logging in (as opposed to signing up) is always the returning-user
    // story — reseed THIS instance (not just the flag for next load: the
    // instance already under our feet may have been constructed empty, from
    // an earlier signup's persisted flag) and clear the flag for future loads.
    this.seedDemoData();
    this.setEmptyAccount(false);
    this.persistSession(user);
    return user;
  }

  async signup({ name, email, password }: SignupInput): Promise<User> {
    await sleep(800);
    if (password.length < 8) {
      throw new ApiError("Password must be at least 8 characters.", 422);
    }
    const user: User = { id: "u_demo", name, email, plan: "free" };
    // Signup must exercise a truthful first-user state. Seeded agency data is
    // useful for returning-user screenshots, but showing it to a new account
    // makes onboarding untestable and reads like a privacy breach. Persisted
    // (not just cleared in memory) so it survives the next page load too —
    // see EMPTY_ACCOUNT_KEY and the constructor above.
    this.clearToEmptyAccount();
    this.cancelRequested.clear();
    this.setEmptyAccount(true);
    this.persistSession(user);
    return user;
  }

  async loginWithProvider(provider: OAuthProvider): Promise<User> {
    // simulate the redirect round-trip
    await sleep(900);
    this.seedDemoData();
    this.setEmptyAccount(false);
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

  private setEmptyAccount(empty: boolean) {
    if (typeof window === "undefined") return;
    if (empty) window.localStorage.setItem(EMPTY_ACCOUNT_KEY, "1");
    else window.localStorage.removeItem(EMPTY_ACCOUNT_KEY);
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
    // clamp on a word boundary — never a mid-word cut before the ellipsis
    // a known demo brief gets its curated label — the report's H1 is a real
    // title, never a clipped prompt (the backend synthesizes titles the same way)
    const curated = DEMO_BRIEFS.find((b) => b.brief === trimmed)?.label;
    const title =
      curated ??
      (trimmed.length > 64
        ? `${trimmed.slice(0, 61).replace(/\s+\S*$/, "").trimEnd()}…`
        : trimmed);
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

    // QA/e2e-only: mock never simulated a held-back output before — every run
    // delivered cleanly, leaving the filter-block UI (page.tsx blockMessage)
    // dark territory with no browser proof. Same keyed-off-brief pattern as
    // the partial-timeout case above.
    if (run.brief.toLowerCase().includes("force a blocked output for e2e")) {
      run.status = "blocked";
      run.blockStage = "filter";
      yield { type: "status", status: "blocked" };
      return;
    }

    // Output filter cleared — stream the report in word chunks. Event order
    // mirrors the real backend: deltas → report_done → status:delivered
    // (a DELIVERED badge over a still-streaming report is a contract breach).
    const report = `# ${run.title}\n${SAMPLE_REPORT.split("\n").slice(1).join("\n")}`;
    run.status = "delivered";

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
    // Every normal delivery here really did pass the simulated output filter
    // (the decision log above always logs "verdict=pass") — declaring it
    // grounded is honest, not decorative, and without it the VERIFIED seal
    // (a real trust signal, INTEGRATION_CONTRACT.md §5) never once appears
    // in the mock experience, which undersells "claims checked" on every
    // ordinary run.
    run.verificationState = "grounded";
    // QA/e2e-only: the backend's real terminal contract has three independent
    // axes (status / verificationState / completionState — INTEGRATION_
    // CONTRACT.md §"three axes"), and the common degraded case is delivered +
    // grounded + partial all at once. Nothing else in the mock ever reaches
    // that combination, so there was no way to browser-exercise the
    // completion-status UI without this. Keyed off brief text, like the
    // landing demo's curated titles, never surfaced as a suggestion.
    if (run.brief.toLowerCase().includes("force a partial timeout for e2e")) {
      run.completionState = "partial";
      run.completionReason = "timeout";
    }
    yield { type: "report_done" };
    yield { type: "status", status: "delivered" };

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

  async hydrationPreview(brief: string, projectId?: string): Promise<HydrationPreviewEntry[]> {
    await sleep(180);
    // keyword-overlap stand-in for the backend's real trust+similarity ranking.
    // Mirrors its scoping rule: projectId filters wiki only; learned tiers are
    // account-wide. Learned-tier hits get synthetic render-only ids.
    const terms = brief.toLowerCase().split(/[^a-z0-9]+/).filter((t) => t.length > 2);
    if (terms.length === 0) return [];
    return this.memory
      .filter((m) => m.tier !== "wiki" || !projectId || m.projectId === projectId)
      .map((m, n) => {
        const hay = `${m.title} ${m.content}`.toLowerCase();
        let hits = 0;
        for (const t of terms) if (hay.includes(t)) hits += 1;
        const score = Math.min(1, (hits + (m.tier === "wiki" ? 0.5 : 0)) / (terms.length + 0.5));
        return {
          hits,
          hit: {
            ...structuredClone(m),
            id: m.tier === "wiki" ? m.id : `preview_${n}`,
            score,
          },
        };
      })
      .filter((x) => x.hits > 0)
      .sort((a, b) => b.hit.score - a.hit.score)
      .slice(0, 8)
      .map((x) => x.hit);
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
    // Returning demo accounts get a plausible history. A genuinely empty
    // signup must stay empty; fabricated usage there breaks user trust.
    const BASELINE = [
      88_000, 0, 142_000, 205_000, 64_000, 0, 176_000,
      238_000, 121_000, 96_000, 31_000, 158_000, 297_000, 184_000,
    ];
    const byDay = Array.from({ length: days }, (_, i) => {
      const date = new Date(Date.now() - (days - 1 - i) * 86_400_000)
        .toISOString()
        .slice(0, 10);
      const fromRuns = runs
        .filter((r) => r.createdAt.slice(0, 10) === date)
        .reduce((sum, r) => sum + (r.tokensUsed ?? 0), 0);
      return { date, tokens: fromRuns + (runs.length > 0 ? (BASELINE[i] ?? 0) : 0) };
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
