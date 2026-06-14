# Frontend ⇆ Backend integration spec (complete — build from this, don't guess)

You are a Claude Code instance working in `frontend/`. This is the **complete,
authoritative, self-contained** description of what the backend serves today, what's
built but not yet rendered, and what's coming — plus the exact frontend edits for
each. **Build entirely from this doc. Do NOT read the backend code** under
`../backend/`: it is being actively changed in parallel (new experts + media
support), so reading it now could mislead you — and you don't need to. Every shape
your work touches is FROZEN and fully specified below; the HTTP contract does not
change under the work coming to the backend (it only adds, and the headroom notes in
§9 cover that). If something genuinely seems missing here, ask the human — do not go
spelunking the in-flux backend.

> READ FIRST: `frontend/AGENTS.md` — this is **Next.js 16 + React 19**, with
> breaking changes from your training data. Read the guides in
> `node_modules/next/dist/docs/` before writing any component/route code. The
> design system is fixed: every color is a token in `src/config/theme.config.ts`;
> the six files in `src/config/` (`app`, `brand`, `nav`, `plans`, `site`, `theme`)
> control the app. Work phone-first (verify at **390px**), touch as primary pointer.
> Don't add a component library — harden the hand-built primitives.

---

## 0. The one mental model

Components NEVER call `fetch` or know a URL. They call hooks in
`src/lib/api/hooks.ts`, which call `getClient()` (`src/lib/api/index.ts`), which
returns ONE of two implementations of the `ClannonClient` interface
(`src/lib/api/client.ts`):

- **`mock.ts`** — the bundled simulator. Default. Powers the demo + offline dev.
- **`http.ts`** — the real FastAPI client.

Which one is chosen: `appConfig.apiMode` (`src/config/app.config.ts`), from
`NEXT_PUBLIC_API_MODE`. **So: any new capability must be added to the interface
(`client.ts`) AND both implementations (`mock.ts`, `http.ts`), or the app breaks in
one mode.** This is the single most important rule. Types live in
`src/lib/api/types.ts` and mirror the backend's JSON field names exactly.

### Switch to the real backend (no component edits)

`src/config/app.config.ts` reads these env vars (put them in `frontend/.env.local`):

```
NEXT_PUBLIC_API_MODE=http
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000   # FastAPI host; Railway URL in prod. No trailing slash.
```

Run the backend: `cd ../backend && uvicorn api.app:app --port 8000` (full runs also
need `docker compose up -d clamav qdrant` from the repo root). The backend must set
`FRONTEND_ORIGIN` to your exact frontend origin (e.g. `http://localhost:3000`) —
CORS uses `allow_credentials=True`, which forbids `*`, so the origin must match
exactly or cookies are blocked.

---

## 1. Auth model (already wired in `http.ts`)

- Cookie session. The backend sets an **httpOnly** cookie `clannon_session`
  (14-day TTL) on `signup`/`login`. JS never sees it — **do not** store tokens.
- Every request uses `credentials: "include"` (set in `appConfig.http`). Keep it.
- `GET /auth/me` → `User` when logged in, **401** when not. `http.ts`'s `me()`
  maps 401 → `null` (not an error) — that's how the app knows you're logged out.
- `logout` → 204, clears the cookie.
- OAuth (`loginWithProvider`) is a full-page navigation to
  `/auth/oauth/:provider`; today the backend 302-redirects back to
  `/login?error=oauth_unavailable` (Supabase OAuth lands later). The mock resolves
  a fake user. Leave the button; it degrades gracefully.
- **Cross-origin in prod:** frontend (Vercel) and backend (Railway) are different
  hosts. For cookies to flow the backend cookie must be `SameSite=None; Secure`
  (it has `SERVER_COOKIE_SECURE`); that's a backend deploy detail, but it affects
  you for artifact downloads (see §6 — use the fetch-blob path, not a bare `<a>`).

---

## 2. Complete endpoint reference

Base URL = `appConfig.apiBaseUrl`. All under it. `:id`/`:name`/`:provider` are
substituted by `http.ts`'s `url()` helper. Auth = the session cookie (sent
automatically); unauthenticated calls to protected routes return **401**.

| Method | Path | Request | Response | Notes |
|---|---|---|---|---|
| GET | `/config` | — | `RemoteConfig` | Public, unauth. `{version, plans, features, limits}`. Overrides local defaults. Returns null-handling in client when absent. |
| POST | `/auth/signup` | `{name, email, password}` JSON | `User` + sets cookie | password ≥ 8 chars; name 2–80. 429 on rate limit. |
| POST | `/auth/login` | `{email, password}` JSON | `User` + sets cookie | 401 on bad creds; 429 rate-limited. |
| POST | `/auth/logout` | — | 204 | clears cookie. |
| GET | `/auth/me` | — | `User` or **401** | client maps 401 → null. |
| GET | `/auth/oauth/:provider` | — (navigation) | 302 → frontend | `?error=oauth_unavailable` until Supabase. |
| GET | `/runs` | — | `RunSummary[]` | the user's runs, newest first. |
| POST | `/runs` | **multipart**: `brief` + optional `files` | `{id}` | **CHANGED — was JSON. See §5.** Starts the pipeline in the background. 422 if a file is rejected. |
| GET | `/runs/:id` | — | `Run` (full) | 404 if not the user's run. |
| GET | `/runs/:id/stream` | — (SSE) | `text/event-stream` of `RunEvent` | see §4. |
| GET | `/runs/:id/artifacts/:name` | — | file **bytes** (`Content-Disposition: attachment`) | **NEW. See §6.** 404 unless the run published that exact name. |
| POST | `/runs/:id/feedback` | `{rating: "up"\|"down"\|null, comment?}` | 204 | thumbs on a delivered run. |
| POST | `/runs/:id/followup` | `{brief}` JSON | `{id}` | next turn of the same session. **Text-only today** (no files). |
| GET | `/runs/:id/thread` | — | `Run[]` | all turns of the session, oldest first. |
| GET | `/memory` | — | `MemoryEntry[]` | wiki entries (from SQLite) + episodic (from run memory writes). |
| POST | `/memory` | `{tier, title, content}` | `MemoryEntry` | **only `tier:"wiki"`**; other tiers → 403 (pipeline-written). |
| PUT | `/memory/:id` | `{tier, title, content}` | `MemoryEntry` | 404 if not found. |
| POST | `/memory/upload` | **multipart** `files` (.md/.txt) | `MemoryEntry[]` | ≤10 files, ≤512 KB each. Already wired. |
| DELETE | `/memory/:id` | — | 204 | 404 if not found. |
| GET | `/usage` | — | `UsageSummary` | token metering placeholder (zeros until Redis budgets land). |
| GET | `/settings/models` | — | `LayerModelConfig[]` | per-layer model choices; locked layers read-only. |
| PUT | `/settings/models` | `{layer, model}` | 204 | 403 locked, 404 unknown layer, 422 model not in options. `layer` may be `"expert:<key>"`. |
| POST | `/billing/checkout` | `{planId}` | **501** today | Stripe lands with cloud. |
| POST | `/billing/portal` | — | **501** today | same. |

---

## 3. Every data type (TS, matches backend JSON exactly)

These are in `src/lib/api/types.ts`. Current ones are correct; the **two marked
NEW** must be added (see §5/§6). Backend sends camelCase for run/user shapes
EXCEPT artifact (snake_case `run_id`) — noted inline.

```ts
type RunStatus =
  | "queued" | "sanitizing" | "verifying" | "orchestrating"
  | "filtering" | "delivered" | "blocked" | "failed";

type DecisionKind =
  | "hydration" | "route" | "expert_spawn" | "tool_call"
  | "observation" | "answer" | "warning" | "error";

interface DecisionLogEntry {
  id: string;            // "log_<hex>"
  ts: string;            // ISO
  kind: DecisionKind;
  title: string;         // the human line ("calling web_search", "requesting memory hydration")
  detail?: string;       // (unused by backend today)
  meta?: Record<string, string>;  // string→string map, e.g. {expert:"web.research", domain:"market"}
}

type ExpertStatus = "spawned" | "working" | "summarizing" | "done" | "failed";
interface ExpertState {
  id: string;            // "e1", "e2", ...
  name: string;          // expert key, e.g. "web.research"
  domain: string;        // free-form domain label
  status: ExpertStatus;
  summary?: string;      // brief structured summary (truncated to 400 chars)
  toolCalls: number;
}

interface Source { id: string; title: string; url: string; domain: string; }  // [] today; citation expert fills it (§9)

interface RunSummary {
  id: string;            // "run_<hex>"
  title: string;         // brief, truncated to 64
  status: RunStatus;
  createdAt: string;     // ISO
  tokensUsed: number;
  expertCount: number;
  sessionId?: string;    // groups turns into a thread
}

interface Run extends RunSummary {
  brief: string;
  decisionLog: DecisionLogEntry[];
  experts: ExpertState[];
  report?: string;            // markdown; present once the output filter clears it
  sources: Source[];          // [] today
  artifacts: Artifact[];      // NEW — see §6
  inputs: InputFileMeta[];    // NEW — see §5
  feedbackRating?: "up" | "down" | null;
  feedbackComment?: string | null;
  parentRunId?: string | null;
  sessionId?: string;
  blockStage?: "sanitize" | "verify" | "filter" | "security" | null;  // set when status==="blocked"
}

// NEW (§6) — backend sends snake_case run_id
interface Artifact { id: string; run_id: string; name: string; mime: string; size: number; }
// NEW (§5)
interface InputFileMeta { name: string; modality: string; size: number; }

// SSE — one per `data:` line
type RunEvent =
  | { type: "status"; status: RunStatus }
  | { type: "log"; entry: DecisionLogEntry }
  | { type: "expert"; expert: ExpertState }
  | { type: "sources"; sources: Source[] }      // not emitted yet; keep for §9
  | { type: "report_delta"; text: string }
  | { type: "report_done" }
  | { type: "usage"; tokensUsed: number };

interface MemoryEntry {
  id: string; tier: "wiki" | "semantic" | "episodic" | "procedural";
  title: string; content: string; updatedAt: string;
  confidence?: number; source?: string;   // semantic tier
  runId?: string;                          // episodic tier
}

interface User { id: string; name: string; email: string; plan: PlanId; }
interface UsageSummary { periodStart: string; periodEnd: string; budget: number; used: number; byDay: { date: string; tokens: number }[]; }

type PipelineLayer = "verifier" | "orchestrator" | "experts" | "filter";
interface LayerModelConfig {
  layer: PipelineLayer; label: string; description: string;
  model: string; options: string[]; locked?: boolean;
  experts?: { key: string; label: string; model: string }[];  // only on the "experts" layer
}

interface RemoteConfig {
  version?: string;
  plans?: Plan[];                              // overrides src/config/plans.ts
  features?: { demo?: boolean; billing?: boolean };
  limits?: { briefMinChars?: number };
}
```

**`/config` returns today** (from `backend/api/config.py`): `version:"0.1-dev"`,
4 plans (`free` Seedling / `starter` $29 / `pro` $79 / `agency` $199 — token
budgets 100k/2M/6M/20M, memoryTiers per plan), `features:{demo:true,billing:true}`,
`limits:{briefMinChars:2}`. `/settings/models` today returns just **orchestrator**
and **experts** layers (both unlocked, default `gemini-3.1-flash-lite`); verifier +
filter are commented out (locked layers come back later). The experts layer carries
a per-expert list (`web.research`, `synthesis.writer` today). **Do not hard-code any
of this — render whatever `/config` and `/settings/models` send.**

---

## 4. Run lifecycle + the SSE protocol (precise)

**Create → stream → fetch.** `POST /runs` returns `{id}` immediately and runs the
pipeline in the background. Subscribe to `GET /runs/:id/stream` for live events;
when it closes, `GET /runs/:id` has the final `Run`.

**Status machine:** `queued → sanitizing → verifying → orchestrating → filtering →
delivered`. Terminal states: `delivered` | `blocked` | `failed`. On `blocked`,
`blockStage` says which gate: `sanitize`/`verify` (input-side — nothing reached the
models) vs `filter` (output-side — a draft was produced then held) vs `security`.

**SSE frame format:** each message is `data: <json>\n\n`. `<json>` is one
`RunEvent`. The stream replays buffered events first (so a late subscriber catches
up), then streams live ones, then the server sends a sentinel and closes.
`http.ts`'s `streamRun` already: splits on `\n\n`, reads `data:` lines, `JSON.parse`s
each, **skips malformed/`[DONE]` frames**, and ends on stream close. Keep that
tolerance — unknown future event types must not crash it.

**Event order (typical):** `status:orchestrating` → `log`(hydration) →
`expert`(spawned/working) → many `log`(tool_call/observation) →
`expert`(done) → `status:filtering` → `report_delta`×N → `report_done` →
`status:delivered`. `usage` can arrive anytime. `report_delta.text` chunks
concatenate into the markdown report. A `blocked`/`failed` run emits the terminal
`status` and no/partial report.

---

## 5. GAP 1 — Uploads IN (a run can carry input files)

The backend accepts input files on run creation (CSV to analyze, code to work on,
PDF). They're malware-scanned at the boundary and seeded into the expert's sandbox
with **original bytes** (clean files are not redacted). **Scope today: text-family
files + PDF, max 10.** `Run.inputs` lists what was attached (name/modality/size).

**`POST /runs` is now `multipart/form-data`** — field `brief` (text) + repeated
field `files`. It is no longer a JSON body. Mirror the existing `uploadMemoryFiles`
in `http.ts` (it already does multipart correctly).

### Exact edits

1. **`src/lib/api/types.ts`** — add `InputFileMeta` (§3) and `inputs: InputFileMeta[]`
   to `Run`.
2. **`src/lib/api/client.ts`** — change the interface:
   ```ts
   createRun(brief: string, files?: File[]): Promise<{ id: string }>;
   ```
3. **`src/lib/api/http.ts`** — replace `createRun`:
   ```ts
   async createRun(brief: string, files: File[] = []): Promise<{ id: string }> {
     const form = new FormData();
     form.append("brief", brief);
     for (const f of files) form.append("files", f, f.name);   // field name MUST be "files"
     const res = await fetch(url(appConfig.endpoints.createRun), {
       method: "POST",
       credentials: appConfig.http.credentials,
       body: form,                          // do NOT set Content-Type; browser sets the boundary
     });
     if (!res.ok) {
       let message = res.statusText;
       try { message = errorMessage(await res.json(), message); } catch {}
       throw new ApiError(message, res.status);   // 422 detail = which file was rejected, show it
     }
     return (await res.json()) as { id: string };
   }
   ```
4. **`src/lib/api/mock.ts`** — accept `files?: File[]`; build a mock `inputs` array
   (`files.map(f => ({name:f.name, modality: f.type.includes("pdf")?"pdf":"text", size:f.size}))`)
   and attach it to the created run so the UI is testable in mock mode.
5. **`src/lib/api/hooks.ts`** — `useCreateRun` mutationFn becomes
   `(vars: { brief: string; files?: File[] }) => getClient().createRun(vars.brief, vars.files)`.
   (Update its one caller in the composer accordingly.)
6. **Composer** (`src/app/app/page.tsx`) — add a file-attach control to the main
   composer. Validate client-side to MATCH the backend (text-family files, PDF, and
   **images** — audio/video land next; ≤10 files; ≤50 MB each) but let the backend
   stay the authority: on a 422, surface
   its `detail` message verbatim (it names the rejected file + reason). Show
   selected files as removable chips before submit.
7. **Run view** (`src/app/app/runs/[id]/page.tsx`) — render `run.inputs` as a quiet
   "Attached" chip row near the brief (filename + size, a file-type icon).
8. **Follow-up composer** stays text-only (the backend `followup` route takes no
   files yet) — don't show attach there.

---

## 6. GAP 2 — Artifacts OUT (a run can deliver files)

Experts produce artifact files (a generated report, a code file; charts/media
later) captured to durable storage. They're on the finished `Run` and downloadable.

- `GET /runs/:id` → `Run.artifacts: Artifact[]`, each `{id, run_id, name, mime, size}`.
- `GET /runs/:id/artifacts/:name` → the bytes, `Content-Disposition: attachment`,
  `Content-Type: <mime>`. **404 unless the run actually published that name** (the
  run's own artifact list is the auth boundary — so only render links for names in
  `run.artifacts`).

### Exact edits

1. **`src/lib/api/types.ts`** — add `Artifact` (§3, note `run_id` snake_case) and
   `artifacts: Artifact[]` to `Run`.
2. **`src/config/app.config.ts`** — add to `endpoints`:
   `runArtifact: "/runs/:id/artifacts/:name",`.
3. **`src/lib/api/client.ts`** + **`http.ts`** + **`mock.ts`** — add
   `downloadArtifact(runId: string, name: string): Promise<Blob>`. In `http.ts`:
   ```ts
   async downloadArtifact(runId: string, name: string): Promise<Blob> {
     const res = await fetch(url(appConfig.endpoints.runArtifact, { id: runId, name }), {
       credentials: appConfig.http.credentials,   // cross-origin cookie → fetch, not a bare <a>
     });
     if (!res.ok) throw new ApiError(`Download failed: ${res.statusText}`, res.status);
     return res.blob();
   }
   ```
   In `mock.ts` return a small `new Blob(["mock artifact"], {type:"text/plain"})`.
   **Why fetch-blob, not `<a href download>`:** the backend is a different origin and
   auth is a cookie — a fetch with `credentials:"include"` reliably authenticates;
   a bare cross-site `<a download>` may not send the cookie. Trigger the save with
   `URL.createObjectURL(blob)` → temporary `<a>` → `revokeObjectURL`.
4. **Run view** (`src/app/app/runs/[id]/page.tsx`) — add an "Artifacts" / "Files"
   block in the report area, shown only when `run.artifacts.length > 0`: each row =
   name + type + human size + a download button calling `downloadArtifact`. The
   report markdown may mention files by name; this list is the canonical download UI.

---

## 7. The `useLiveRun` carryover bug (real — fix it)

`useLiveRun` (`src/lib/api/hooks.ts`) guards re-subscription with
`startedFor.current === run.id`, but it **never resets `state`** when `run.id`
changes. So when you navigate from one non-terminal run to another, the old run's
`log`/`experts`/`reportText` stay in `state`, and the render-time merge
(`state.log.length ? state.log : run.decisionLog`) shows the STALE log/report until
the new stream produces its first events. Fix: reset `state` to the initial empty
shape when the id changes, before subscribing. Concretely, at the top of the effect
(after the terminal/guard checks, before `startedFor.current = run.id`), set state
back to the initial object (status `"queued"`, empty arrays/strings, `live:false`).
Keep the merge logic. Verify by starting run A, then opening run B mid-stream: B
must not flash A's decision log.

---

## 8. Other UI/UX fixes (from the review — `.judments/UI_UX.MD`, 8.2/10)

Do these; they're the gap to god-tier. Keep what's praised (centralized tokens, the
run page, the API architecture, security headers, no `dangerouslySetInnerHTML`).

1. **Marketing overclaim.** "every claim is checked", "PII never leaves", "6–10
   hours in ~20 minutes", "a report you can put your name on" — substantiate or
   soften before launch (these live in the marketing sections +
   `src/config/site.config.ts`). It reads as sophisticated slop otherwise.
2. **Client-heavy load.** Many `"use client"` files, incl. static marketing that
   can be server components. Trim for first-load speed where there's no interactivity.
3. **Custom primitives a11y.** Tabs, dialog, command palette, listbox are good but
   not library-grade. Harden the **command palette** especially: focus trap, roving
   tabindex, aria roles, Escape, SR labels. Don't add a component lib.
4. **Metaphor restraint.** The "Botanical Archive" voice ("plant the first ring",
   "this branch doesn't exist", "rings", "grown/pruned") is charming but, overused,
   reads unserious to a B2B buyer. Keep it; sharpen it — especially in the
   error/empty states a paying user hits.

---

## 9. What's COMING — build with headroom (do NOT build yet; just don't block it)

The backend's next initiative (#2) is **all-media + the full expert roster**. None
of this changes the existing contract; it ADDS. Design so it slots in:

- **All media inputs.** Upload-IN now accepts **images** too (the **Media Expert**,
  `media.analyst`, reads them via Gemini multimodal); **audio / video** come next.
  `InputFileMeta.modality` is `"image"` for an image (and will gain `"audio"|"video"`).
  The "Attached" chip row (§5) should pick an icon by modality and not assume text.
- **More experts.** The roster keeps growing (documentation, summarization, and
  more next). Live today: web.research, synthesis.writer, verification.claims,
  code.engineer, data.analyst, and **media.analyst**. The decision log + expert panel
  already render whatever `name`/`domain` the backend streams, so **new experts appear
  automatically — make sure NO component hard-codes an expert list** (the only expert
  list to render dynamically is from `/settings/models`'s `experts` array).
- **Sources will populate.** `Run.sources` is `[]` today; the **citation** expert
  fills it (and a `{type:"sources"}` SSE event may start arriving — the union and
  `useLiveRun` already handle it). The sources panel exists; keep it.
- **More artifact types.** Charts/images as artifacts later — `Artifact.mime` tells
  you how to render/label; show an image preview when `mime.startsWith("image/")`,
  else a download row.
- **Plans/models are backend-driven.** When tiers/models change, `/config` and
  `/settings/models` change; the UI must keep rendering them dynamically (it does).

---

## 10. Frontend file map (where to work)

- `src/lib/api/` — `client.ts` (interface), `http.ts` (real), `mock.ts` +
  `mock-data.ts` (simulator), `types.ts` (shapes), `hooks.ts` (react-query hooks +
  `useLiveRun`), `index.ts` (`getClient()` picks impl from `appConfig.apiMode`).
- `src/config/` — `app.config.ts` (endpoints + http + limits), `plans.ts`,
  `theme.config.ts` (all colors), `site.config.ts` (copy/marketing), `brand`, `nav`.
- `src/app/app/page.tsx` — the workspace/composer (run creation, §5).
- `src/app/app/runs/[id]/page.tsx` — the run view (stream, decision log, experts,
  sources, report, feedback, follow-up; render `inputs` §5 + `artifacts` §6 here).
- `src/app/app/memory/`, `src/app/app/settings/` — memory archive, model settings.
- `src/app/(marketing)` + `login`/`signup`/`legal` — public pages.

---

## 11. Error handling contract

FastAPI errors come back as `{detail: ...}`. `detail` is a **string** for
`HTTPException` but an **array** of `{msg,...}` for Pydantic 422 validation errors.
`http.ts`'s `errorMessage()` already coerces both to readable prose — reuse it for
any new fetch (the multipart createRun/upload/download bypass the JSON `request()`
helper, so they must call `errorMessage` themselves, as shown in §5/§6). Network
failure / timeout → `ApiError(message, 0)`. A 401 anywhere means the session expired
— `me()` returning null drives the logged-out UI.

---

## 12. Done =

- `NEXT_PUBLIC_API_MODE=http` against a local backend: sign up/in; create a run
  **with and without a file**; watch it stream (status, decision log, experts,
  report); see the delivered report; **download an artifact**; see **attached
  inputs**; submit a follow-up; rate it — all with **zero console errors**.
- Switching between two live runs does not flash the previous run's log/report (§7).
- **Mock mode still works** (demo + offline dev intact) — every new client method
  exists in `mock.ts` too.
- `npm run lint`, `npm run typecheck`, `npm run build` all pass.
- Verified at **390px** (phone-first), in **light and dark** themes.

If a shape genuinely seems unspecified here, ask the human — do NOT read the in-flux
backend. The backend stays the enforcing authority for every limit; the UI shows, it
never guards.
