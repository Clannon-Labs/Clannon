# Frontend ⇆ Backend integration brief

You are a Claude Code instance working in `frontend/`. This file tells you exactly
what the real backend now exposes, what the frontend hasn't caught up to yet, and
the UI/UX work to do. Read `frontend/AGENTS.md` first (this is NOT the Next.js in
your training data — read the guides in `node_modules/next/dist/docs/` before
writing code). The design system is sacred: every color token lives in
`src/config/theme.config.ts`; six config files in `src/config/` control the app.
Work phone-first (verify at 390px), touch as the primary pointer.

The backend is the source of truth for the HTTP contract:
**`../backend/api/README.md`** (endpoint table) and the FastAPI app in
`../backend/api/app.py`. The frontend mirrors those shapes in
`src/lib/api/types.ts` so JSON passes through without remapping.

---

## 0. Current state

- The app is **mock-backed** by default. `src/lib/api/` has a `ClannonClient`
  interface (`client.ts`) with two implementations: `mock.ts` (bundled, drives
  the demo + dev) and `http.ts` (talks to the real FastAPI). The active one is
  chosen by `appConfig.apiMode` (`src/config/app.config.ts`).
- The **real backend is live and complete** for the core loop: auth (cookie
  session), runs (create → SSE stream → delivered/blocked/failed), follow-ups,
  memory (wiki CRUD + upload), usage, per-layer model settings. It now ALSO has
  two things the frontend does not render yet: **file uploads INTO a run** and
  **artifact files OUT of a run** (details below).
- The backend moved: it deploys from `../backend/` (Railway); the API lives at
  `backend/api/`. This does NOT change the HTTP contract — same routes, same JSON.

### Switching to the real backend

No component changes needed — flip env (`src/config/app.config.ts` reads these):

```
NEXT_PUBLIC_API_MODE=http
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000   # the FastAPI host (Railway URL in prod)
```

Run the backend locally: `cd ../backend && uvicorn api.app:app --port 8000`
(needs `docker compose up -d clamav qdrant` from the repo root for full runs).
Cookies are httpOnly and set by the backend; never store tokens in JS. CORS is
gated by the backend's `FRONTEND_ORIGIN` — set it to your dev origin.

---

## 1. Run lifecycle + SSE (already wired, for context)

`POST /runs` → `{id}`, then `GET /runs/:id/stream` (SSE) emits `RunEvent`s
(`status` / `log` / `expert` / `report_delta` / `report_done` / `usage`), then
`GET /runs/:id` returns the full `Run`. Status flows
`queued → sanitizing → verifying → orchestrating → filtering → delivered`
(or `blocked` with a `blockStage`, or `failed`). `streamRun` in `http.ts` already
parses the SSE frames. `useLiveRun` (`src/lib/api/hooks.ts`) folds events into
state. (See the carryover bug in §4.)

---

## 2. GAP TO CLOSE — Uploads IN (a run can carry input files)

The backend now accepts **input files** on run creation (a CSV to analyze, code
to work on). They are malware-scanned at the boundary and seeded into the expert's
sandbox; a clean file is passed through with full fidelity. Scope today:
text-family files + PDF, max 10.

**Contract change (breaking):** `POST /runs` is now **`multipart/form-data`** — a
`brief` text field plus optional `files`. It is no longer a JSON body. (Mirror the
existing `uploadMemoryFiles` in `http.ts`, which already does FormData correctly.)

The full `Run` now includes an `inputs` array — metadata for the files that were
attached (name / modality / size), so the run view can show "attached: sales.csv".

**Do this:**

1. `src/lib/api/types.ts`
   - Add `export interface InputFileMeta { name: string; modality: string; size: number; }`
   - Add `inputs: InputFileMeta[];` to `interface Run`.
2. `src/lib/api/client.ts` — change the interface method:
   `createRun(brief: string, files?: File[]): Promise<{ id: string }>;`
3. `src/lib/api/http.ts` — make `createRun` multipart:
   ```ts
   async createRun(brief: string, files: File[] = []): Promise<{ id: string }> {
     const form = new FormData();
     form.append("brief", brief);
     for (const f of files) form.append("files", f, f.name);
     const res = await fetch(url(appConfig.endpoints.createRun), {
       method: "POST", credentials: appConfig.http.credentials, body: form,
     });
     // ...same error handling as uploadMemoryFiles, then return res.json()
   }
   ```
   (Do NOT set Content-Type — the browser sets the multipart boundary. The JSON
   `request()` helper would corrupt it; that is why uploads bypass it.)
4. `src/lib/api/mock.ts` — accept the optional `files`, echo them into a mock
   `inputs` array on the created run so the UI can be built/tested without a backend.
5. **Composer UI** (`src/app/app/page.tsx`): add a file-attach affordance to the
   main composer (and the follow-up composer if you want parity — note the backend
   followup is text-only for now, so gate attach to new runs). Validate client-side
   to match the backend (text-family + PDF, ≤10 files, ≤50MB each) but let the
   backend stay the authority — surface its 422 reason verbatim on rejection.
6. **Run view** (`src/app/app/runs/[id]/page.tsx`): render `run.inputs` as a small
   "Attached" chip row near the brief (filename + size). Keep it quiet, not loud.

A 422 from `POST /runs` with a readable `detail` means a file was rejected
(unsupported type / too big / malicious / unscannable) — show that message.

---

## 3. GAP TO CLOSE — Artifacts OUT (a run can deliver files)

Experts now produce **artifact files** (a generated report, a code file, later a
chart) captured to durable storage. They appear on the finished `Run` and are
downloadable.

- `GET /runs/:id` → `Run.artifacts: Artifact[]` where each is
  `{ id, run_id, name, mime, size }`.
- `GET /runs/:id/artifacts/:name` → the file bytes
  (`Content-Disposition: attachment`). 404 unless the run actually published that
  name (the run's own artifact list is the auth boundary).

**Do this:**

1. `src/lib/api/types.ts`
   - `export interface Artifact { id: string; runId: string; name: string; mime: string; size: number; }`
     (the backend sends snake_case `run_id`; either map it in the client or accept
     `run_id` in the type — pick one and be consistent. The other fields match.)
   - Add `artifacts: Artifact[];` to `interface Run`.
2. `src/config/app.config.ts` — add an endpoint:
   `runArtifact: "/runs/:id/artifacts/:name"`.
3. `src/lib/api/client.ts` + `http.ts` + `mock.ts` — add
   `artifactUrl(runId: string, name: string): string` (just builds the URL via
   `appConfig`) so the run view can render a normal download `<a download>` link.
   A direct link is simpler than fetching blobs and respects the cookie session.
4. **Run view** (`src/app/app/runs/[id]/page.tsx`): add an "Artifacts" / "Files"
   section in the report area listing each artifact (name, type, size) with a
   download action. Only show it when `run.artifacts.length > 0`. The report
   markdown may reference files by name; keep the list as the canonical download
   surface.

---

## 4. UI/UX fixes (from the review — `.judments/UI_UX.MD`, scored 8.2/10)

Address these; they are the gap to "god-tier":

1. **Live-run state carryover (real bug).** `useLiveRun` (`src/lib/api/hooks.ts`)
   does not visibly reset streamed log/report state when the run id changes from
   one non-terminal run to another — old state can leak into a new run view. Reset
   on `id` change (key the effect on id; clear buffered log/report/experts).
2. **Marketing overclaim.** Copy like "every claim is checked", "PII never leaves",
   "6–10 hours in about 20 minutes", "a report you can put your name on" needs
   proof, citations, or softer phrasing before launch — otherwise it reads as
   sophisticated slop. Soften or substantiate (these live in the marketing
   sections + `src/config/site.config.ts`).
3. **Client-heavy load.** Many `"use client"` components, including marketing
   sections that can be (partly) server components. Trim for first-load speed —
   move static marketing to server components where there is no interactivity.
4. **Custom primitives a11y.** Tabs, dialog, command palette, listbox are good but
   not library-grade. Harden the **command palette** especially (focus trap, roving
   tabindex, aria roles, Escape, screen-reader labels). Don't add a component lib;
   harden what exists.
5. **Metaphor restraint.** The "Botanical Archive" voice ("plant the first ring",
   "this branch doesn't exist", "rings", "grown/pruned") is charming but, used too
   often, makes a B2B buyer doubt seriousness. Keep it; use it with a sharper knife
   (especially in error/empty states a paying user hits).

Keep what's excellent: centralized tokens, the run page, the API architecture
(query keys + mock/http isolation), security headers, no `dangerouslySetInnerHTML`.

---

## 5. Coming soon — design with headroom (do NOT build yet, just don't block it)

The backend is expanding next; leave room so these slot in without a redesign:

- **All media inputs.** Upload-IN will extend to image / audio / video (today it's
  text + PDF). The `inputs` chip row should handle non-text icons gracefully.
- **More experts.** The roster is growing to include **media**, **documentation**,
  and **citation** experts. The decision log + expert panel already render whatever
  `domain`/`name` the backend sends, so new experts appear automatically — just
  make sure no hard-coded expert list exists in the UI.
- **Sources will populate.** `Run.sources` is `[]` today; the **citation** expert
  will fill it. The sources panel already exists — keep it.
- **New SSE events are possible** (e.g. an artifact-ready event). `streamRun`
  already skips unknown frames; keep the `RunEvent` union open to extension and
  don't crash on an unrecognized `type`.

---

## 6. Done = 

- `NEXT_PUBLIC_API_MODE=http` against a local backend: create a run (with and
  without a file), watch it stream, see the report, download an artifact, and see
  attached inputs — all without console errors.
- Mock mode still works (so the demo + offline dev are intact).
- `npm run lint` and `npm run build` pass.
- Verified at 390px (phone-first), light and dark themes.

Ask the backend instance (or check `../backend/api/README.md`) if any shape is
unclear. The backend stays the enforcing authority for every limit — the UI shows,
it never guards.
