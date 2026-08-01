# Clannon API server (Vraksha engine)

The FastAPI surface the Clannon frontend talks to. It wraps the existing
pipeline (`core.pipeline.ACTIVE_STAGES`) **without modifying it** and serves
the contract below. This file is the single source of truth for the
backend↔frontend contract — when you add or change an endpoint, update the
table here.

```bash
# canonical local start, from repository root
./dev.sh
```

The launcher starts/reuses ClamAV and Qdrant, waits until both answer, then
starts FastAPI and Next.js. It also replaces stale Clannon-owned listeners,
sets the local embedding cache, and stops both application processes on
`Ctrl-C`.

Local browser traffic has one visible origin:

- `http://<LAN-IP>:3000` — Next.js.
- `http://<LAN-IP>:3000/api/*` — Next.js reverse-proxies to FastAPI.
- `http://127.0.0.1:8000` — private FastAPI listener; not opened to the LAN.

This shape keeps cookies, SSE, and normal requests same-origin in development.
Do not run a second component `dev.sh`; root `dev.sh` is the only launcher.

## Environment

Loads `.env` then `.env.local` from `backend/` (the working directory, same as
`main.py`), so the pipeline gets its provider keys. Server-specific variables:

| Variable | Default | What it does |
|---|---|---|
| `FRONTEND_ORIGIN` | `http://localhost:3000` | The default CORS allow-origin + where OAuth errors redirect. Must exactly match the frontend's origin (scheme + host + port). |
| `SERVER_CORS_ORIGINS` | `=FRONTEND_ORIGIN` | Comma-separated origins allowed to call the API with credentials. Set e.g. `https://clannon.com,https://app.clannon.com` so the marketing apex AND the workspace subdomain can both make authenticated XHR/SSE calls. |
| `SERVER_COOKIE_DOMAIN` | _(unset)_ | Session-cookie `Domain`. Unset = host-only (same-origin dev). Set `.clannon.com` (leading dot) so ONE cookie is valid for the apex and every subdomain — the mechanism behind seamless, no-relogin auth when the workspace moves to `app.clannon.com`. |
| `SERVER_DEFAULT_PLAN` | `free` | Plan for new signups. Use `pro` in local dev to unlock all memory tiers. |
| `SERVER_COOKIE_SECURE` | `0` | Set `1` in production (HTTPS) so the session cookie is Secure. |
| `SERVER_DB_PATH` | `api/data/clannon.db` | SQLite location (users, sessions, projects, wiki, runs, model prefs). |

## Module map

| File | Owns |
|---|---|
| `app.py` | FastAPI assembly, CORS, and core routes. |
| `auth.py` | Users + sessions + the SQLite data layer (projects, wiki, model prefs — every query lives here, never in the routes). Scrypt, httpOnly cookies. The dev stand-in for Supabase — swap this one module when Supabase lands. |
| `runs.py` | Thin façade over run state, storage, execution, inputs, lineage, and SSE. |
| `run_requests.py` | Shared multipart upload admission and per-run model override parsing. |
| `run_revision.py` | Safe revise-turn HTTP route and terminal-target preflight. |
| `run_lineage.py` | Owner-scoped effective-thread resolution, including legacy branches. |
| `run_persistence.py` | Single SQLite row mapping for durable run state. |
| `run_inputs.py` | Persisted upload integrity, revision reuse, and bounded prior-file reseeding. |
| `config.py` | The `/config` payload (plans/features/limits) + server settings. |
| `memory_entitlements.py` | The sole plan → durable-memory-tier authorization policy, derived from central `config.PLANS` and fail-closed for unknown/malformed plans. |

## The contract

Auth is an httpOnly session cookie (`clannon_session`); every endpoint except
`/config` and the auth routes requires it and is scoped to the signed-in user.
JSON keys are camelCase to match the frontend types in
`clannon/frontend/src/lib/api/types.ts`.

| Endpoint | Method | Request | Response |
|---|---|---|---|
| `/config` | GET (public) | — | `RemoteConfig` `{version, plans, features, limits}` |
| `/auth/signup` | POST | `{name, email, password}` | `User`, sets cookie |
| `/auth/login` | POST | `{email, password}` | `User`, sets cookie |
| `/auth/logout` | POST | — | 204, clears cookie |
| `/auth/me` | GET | — | `User` or 401 |
| `/auth/oauth/:provider` | GET (navigation) | — | 302 → frontend (`?error=oauth_unavailable` until Supabase OAuth) |
| `/projects` | GET | — | `Project[]` `{id, name, color?, createdAt}`, newest activity first. A project = a client / body of work; runs + memory scope to it. The "current project" is client-side state (sent as `projectId` per request) — no server-side active project |
| `/projects` | POST | `{name, color?, seedFacts?}` | created `Project`. `seedFacts` (optional markdown): also creates a first WIKI entry in the project titled `Client: <name> — context` (the onboarding "tell Clannon about this client" step). Requires WIKI entitlement; otherwise 403 and neither project nor seed is created |
| `/projects/:id` | PATCH | `{name}` | renamed `Project` (404 if not the caller's) |
| `/projects/:id` | DELETE | — | `204` cascade: deletes the project AND its runs (+ their stored files) AND its wiki/memory scope. Owner-scoped + idempotent (same semantics as `DELETE /sessions/:id`). The learned cross-session memory (Qdrant tiers) is retained |
| `/runs` | GET | `?projectId=<id>` (optional) | `RunSummary[]` — filtered to one project when `projectId` is given, all of the user's effective runs when omitted. Superseded turns never appear. Each `RunSummary`/`Run` carries `tokensUsed`, `cacheReadTokens`, and `cacheWriteTokens`, plus an optional `projectId` |
| `/runs` | POST | `multipart/form-data`: `brief` (text) + optional `files` (input files) + optional `models` (JSON object `role -> model`, per-session model choices) + optional `projectId` (the run is created in that project; an unknown/other-user project is a 422) | `{id}`, starts the pipeline in the background. Each uploaded file is malware-scanned at the boundary (ClamAV/YARA) and seeded into the expert workspace with its original bytes — clean files are NOT redacted; a malicious/unsupported/oversized file is a 422. File scope: text, PDF, image, audio, video; max 10. `models` overrides the user's workspace defaults for this run only (422 on an unknown/locked role or an unavailable model) |
| `/runs/:id` | GET | — | full `Run` (decisionLog, experts, **message**, report, sources, artifacts, inputs, feedbackRating, parentRunId, sessionId, blockStage, verificationState, **completionState**, **completionReason**). `message` = the orchestrator's conversational chat bubble (the agent talking to the user); `report`/`artifacts` = the deliverable. A turn may have `message` only (pure conversation), both, or `report` only. Superseded run IDs return the same non-disclosing `404` as unknown/foreign IDs. |

**Three independent outcome axes — do not collapse them.** A run can be
`delivered` + `grounded` + `partial` all at once, and that combination is
honest, not contradictory:

| Field | Question it answers | Values |
|---|---|---|
| `status` | how did the run's lifecycle end? | `delivered` · `blocked` · `failed` · `cancelled` |
| `verificationState` | did the output filter find the draft grounded? | `grounded` · `partial` · `ungrounded` · `not_applicable` · `null` (filter never ran) |
| `completionState` | did the reasoning loop actually finish the work? | `complete` · `partial` |

`completionState: "partial"` means the orchestrator **degraded**: it hit a
wall-clock timeout, a provider rate-limit storm, or a fault, and answered from
what it had already gathered rather than handing back nothing
(`core/orchestrator/utils/recovery.py`). That answer is real and it is delivered
— which is exactly why `status` alone reads as unqualified success and misleads.
`completionReason` says which: `timeout` · `rate_limit` · `error`.

Set from the orchestrator's own degraded metadata, never inferred from report
text. REST-only today: there is no `completion` SSE event yet, because the event
set is a shared contract with the frontend's `RunEvent` union and adding one
unilaterally breaks `tests/benchmarks/sse_contract_drift.py`. The live-event half
is proposed to the frontend separately.
| `/runs/:id/artifacts/:name` | GET | — | the bytes of one delivered artifact (`Content-Disposition: attachment`). 404 unless the run actually published a file by that name — the run's own artifact list is the auth boundary |
| `/runs/:id/stream` | GET (SSE) | — | `data:` frames, each one JSON `RunEvent`: `status` / `log` / `expert` / `message_delta` / `message_done` / `report_delta` / `report_done` / `sources` / `verification` / `usage`. `message_delta` is the orchestrator's CONVERSATIONAL voice streamed live (it can talk *while experts run*) and is independent of `report_delta` (the deliverable) and `log` (structured ticks); `message_done` closes it. `sources` carries the grounded-search `Source[]` backing a delivered run and is emitted once, just before the report streams (empty when the run ran no grounded search). `verification` carries the output filter's earned-seal verdict (`grounded`/`partial`/`ungrounded`/`not_applicable`), emitted once per run right before the terminal status, only when the filter actually ran — **not yet in the frontend's `RunEvent` union** (flagged, optional UI wiring, see `proposals/`). Terminal `status` values: `delivered` / `blocked` / `failed` / `cancelled` — the stream closes after a terminal status. A reconnect WHILE the run is still live replays its buffered sequence (incl. the message stream) ending in the terminal status; a reconnect AFTER the process has finished persisting it (evicted from the in-memory store to SQLite — `events` is runtime-only, never written through) replays NOTHING and just closes — a client revisiting a past run must fetch `GET /runs/:id` for its content, not rely on the stream replaying it |
| `/runs/:id/cancel` | POST | — | Cooperatively stop an in-flight run. `204` if already terminal (idempotent); normally `200 {status:"cancelling"}` and the authoritative `cancelled` arrives over SSE. The no-live-task edge finalizes directly and returns `cancelled`; if that final write fails it returns/emits `failed` and retains live recovery state rather than falsely claiming cancellation persisted. Ownership-scoped (404 if not caller's run). Cancel ≠ delete — successfully cancelled run stays in history with status `cancelled` (distinct from `failed`/`blocked`). Tokens spent up to stop are charged (usage-based) |
| `/runs/:id/feedback` | POST | `{rating: "up"\|"down"\|null, comment?}` | 204; thumbs rating on a delivered run |
| `/runs/:id/followup` | POST | `multipart/form-data`: `brief` (text) + optional `files` + optional `models` | `{id}`, the next turn of the same session — inherits `sessionId` (`parentRunId` set). Carries input files AND per-session `models` exactly like `POST /runs`; the follow-up run's `inputs` lists the files. The **whole session** is replayed to the orchestrator as real chat history (`message_history`) — every prior turn's brief, conversational message, and report, plus a note of any files each turn attached (trimmed only when the session grows huge, oldest-first). Files uploaded in ANY earlier turn are **persisted and re-seeded** into the expert workspace, so the agent can still read a file referenced several turns later. Only the new brief is sanitized/verified. The follow-up **inherits the parent's `projectId`** (no `projectId` on this endpoint). |
| `/runs/:id/revise` | POST | `multipart/form-data`: required edited `brief`; optional sparse `models`; optional replacement `files`; optional `reuseInputs` boolean (default `true`) | `201 {id}` replaces the target in its existing session. The target and every later effective turn are soft-superseded: hidden from run/history/thread reads, model conversation, recall, and prior-file reseeding, while retained internally for spent-token accounting, saved memory, and audit provenance. The revised run inherits the target's `sessionId`/`projectId`; its parent is the last retained turn or `null` at the root. Target must be terminal (`409` while live). With no replacements, target inputs are reloaded only from namespace-bound authoritative server blobs; new blobs also carry a verified integrity hash, while pre-hash blobs retain namespace + size validation. Missing, malformed, redirected, or hash-mismatched blobs return actionable `409`. Replacement uploads use normal scanning and supersede reuse; `reuseInputs=false` starts without target inputs. Unknown, foreign, or already-superseded target is `404`. |
| `/runs/:id/thread` | GET | — | `Run[]` — effective turns in this conversation, oldest first. Superseded turns are absent; requesting a superseded run ID returns `404`. Legacy pre-existing `lineage_prefix` branches remain readable unless one of their required prefix turns was later superseded. |
| `/runs/:id/audit` | GET | — | Security-decision audit records for this run, owner-scoped. `[]` when the run was not blocked by any security gate or predates the audit trail. `404` when the run is not the caller's. Each record: `{id, traceId, sessionId, blockCode, threatLevel, origin, reason, blockedAt}` — `blockedAt` is ISO 8601 UTC; `blockCode` is the `BlockReason` enum value; `origin` is the blocking gate (`sanitizer`, `verifier`, `filter`); `reason` is the human-readable block explanation, or `null` if the gate did not produce one. |
| `/runs/:id/decisions` | GET | — | Institutional decision-memory records (CB4) for this run, owner-scoped, oldest first. `[]` when the run made no discrete `tool_call`/`answer` decisions (pure narration turns) or predates the audit mirror. `404` when the run is not the caller's. Written for EVERY terminal outcome, not just delivered — a decision on the way to a blocked, failed, or cancelled run is still institutional memory. Each record: `{id, traceId, sessionId, turn, kind, decision, reasoning, participants, decidedAt}` — `kind` is `tool_call` or `answer`; `reasoning` is the best-effort preceding `say()` text, empty string if none; `participants` is the tool/expert key(s) involved. |
| `/sessions/:id` | DELETE | — | Permanently delete a whole conversation (every turn in the session). Owner-scoped and idempotent: `204` whether it deleted turns or there was nothing to delete (a session that isn't the caller's is a no-op `204`, never revealed). Removes the conversation + its turns, and purges its stored files (uploaded inputs AND output artifacts) from disk; the assistant's learned cross-session memory is retained. Any in-flight run in the session is cancelled. |
| `/memory` | GET | `?projectId=<id>` (optional) | Caller-entitled `MemoryEntry[]`: wiki from SQLite plus real Manager-owned semantic/episodic/procedural entries. Both manager request and final serialization are plan-filtered; unknown/malformed plans receive none. Wiki is project-filtered when `projectId` is present; learned tiers remain account-scoped pending memory-layer project scoping |
| `/memory/hydration-preview` | GET | `?brief=<text>&projectId=<id>` (projectId optional) | `(MemoryEntry & {score: number})[]` — plan-filtered dry-run of `MemoryPort.hydrate`, ranked by Manager trust+similarity+recency and capped at 8. Request carries exact allowed tiers; wiki is supplied only when entitled; response is independently filtered if Manager over-returns. Best-effort: brief `<3` chars, degraded memory, or memory fault ⇒ `[]` |
| `/memory` | POST | `{tier:"wiki", title, content, projectId?}` | created entry. Only wiki is user-writable and WIKI entitlement is required (403 otherwise); unknown/other-user `projectId` is 422 |
| `/memory/:id` | PUT / DELETE | entry / — | PUT updates owner-scoped wiki and requires WIKI entitlement. DELETE works across all durable tiers regardless of current plan, preserving deletion/right-to-erasure after downgrade; owner-scoped, unknown/foreign id 404. Wiki UPLOAD `/memory/upload` takes `projectId` as form field or query param and also requires WIKI entitlement |
| `/usage` | GET | — | `UsageSummary` `{periodStart, periodEnd, budget, used, cacheReadTokens, cacheWriteTokens, byDay[]}` — `used` is the REAL metered spend (sum of `run.tokensUsed`, including superseded turns, over a trailing 30-day window), `budget` is the user's plan budget. Runs expose the same cache counters beside `tokensUsed`; providers that report none yield `0`. Cached tokens stay separate because their prices differ: `tokensUsed` remains full-rate input + output and is unchanged. Redis-atomic budget enforcement (decrement + hard stop) lands separately. |
| `/settings/models` | GET / PUT | — / `{layer, model}` | `RoleModelConfig[]` / 204. One entry PER ROLE: 5 selectable (orchestrator, research, planner, code, media_expert) + verifier/filter read-only. Each entry carries `model` (the user's workspace default or the system default), `default`, `options`, `locked`, and `experts` (which experts the role drives). Defaults are derived from `models.yaml` (Claude for reasoning, Gemini for media). PUT sets the per-user WORKSPACE default for a role (403 locked, 422 model not in options). Per-SESSION overrides go on the run POST via `models`. |
| `/billing/checkout` `/billing/portal` | POST | — | 501 until Stripe |

### Terminal presentation

The orchestrator's explicit `presentation` selects the terminal channel; sources
and generated artifacts are delivered metadata and never influence that choice.

- `chat`: accepted output-filter text is persisted on `Run.message` and emitted
  through `message_delta`. It emits no `report_delta` or `report_done`.
- `report`: accepted output-filter text retains the existing terminal order:
  `sources` → `report_delta` × N → `report_done` → terminal `status`.
- `say()` remains live conversational commentary. After substantial tool or
  expert work, accepted final chat follows that commentary. A lone accidental
  `say()` with no recorded tool/expert work remains the sole trivial response.

## How a run streams (the one non-obvious part)

`runs.execute()` builds a `Flow` exactly like `main.py`, replaces
`flow.ctx.decision_log` with a list subclass whose `append` also notifies
subscribers, then steps through `ACTIVE_STAGES` one stage at a time so it can
emit a status transition before each stage. Nothing in `core/` or
`foundation/` is imported differently or patched. When the backend grows a
real queue-backed `DecisionLogSink`, swap the observer for it in one place.

---

## Adding a new endpoint — the full path

Example: you want "archived runs" — `GET /runs/archive`. Six steps, in order.
Steps 1–2 are this repo; 3–6 are the frontend. None of them touch page code
beyond the component that uses the new data.

**1. Server route (`api/app.py`)**

```python
@app.get("/runs/archive")
def archived_runs(user: auth.User = Depends(auth.current_user)) -> list[dict]:
    return [r.summary_json() for r in runs.STORE.list_for(user.id) if r.archived]
```

Rules: take `user` via `Depends(auth.current_user)` for anything private and
filter by `user.id` — never trust ids from the request body. Validate input
with a pydantic `BaseModel`. Return camelCase keys. Raise
`HTTPException(code, "readable message")` for errors — the frontend surfaces
`detail` verbatim.

**2. Update the contract table** in this README.

**3. Frontend route table (`frontend/src/config/app.config.ts`)**

```ts
endpoints: {
  // ...
  runArchive: "/runs/archive",
}
```

`:id`-style segments are substituted automatically by the http client.

**4. Types + client interface (`frontend/src/lib/api/types.ts`, `client.ts`)**

Add the response type to `types.ts` if it's a new shape, then one method on
the `ClannonClient` interface:

```ts
listArchivedRuns(): Promise<RunSummary[]>;
```

**5. Both implementations**

`http.ts` (one liner — the request helper handles auth/timeout/errors):

```ts
listArchivedRuns(): Promise<RunSummary[]> {
  return request(appConfig.endpoints.runArchive);
}
```

`mock.ts` (so the demo and offline dev keep working):

```ts
async listArchivedRuns(): Promise<RunSummary[]> {
  await sleep(250);
  return [];
}
```

TypeScript enforces this: the moment the interface method exists, both
classes fail to compile until implemented — you cannot forget one.

**6. A hook (`frontend/src/lib/api/hooks.ts`) and use it**

```ts
export function useArchivedRuns() {
  return useQuery({ queryKey: ["runs", "archive"], queryFn: () => getClient().listArchivedRuns() });
}
```

Components call the hook; they never know which backend they're on.

**Streaming endpoints** follow the same path but return
`StreamingResponse(generator, media_type="text/event-stream")` server-side
and an `AsyncGenerator` client-side — copy `streamRun` in both `runs.py` and
`http.ts` as the template.

## Deployment (Railway + `clannon.com`)

1. Deploy `backend/` to Railway. Its Docker image starts
   `uvicorn api.app:app` on Railway's `$PORT`.
2. Copy the ignored `backend/.env.prod` template into Railway's
   **Variables → RAW Editor**, replace every `REPLACE_*`, review the staged
   variables, then deploy. The application auto-loads only `backend/.env` and
   `backend/.env.local`; it does **not** auto-load `.env.prod`.
3. Keep this exact production browser boundary:

   ```env
   FRONTEND_ORIGIN=https://clannon.com
   SERVER_CORS_ORIGINS=https://clannon.com
   SERVER_COOKIE_SECURE=1
   SERVER_COOKIE_DOMAIN=.clannon.com
   ```

   Credentialed CORS must use the exact frontend origin, never `*`.
4. Add `https://api.clannon.com` as Railway's custom API domain and point the
   frontend API base URL there. Do not use the raw `*.up.railway.app` origin:
   it is cross-site from `clannon.com`, so the current `SameSite=Lax` session
   cookie will not reliably accompany authenticated fetch or SSE requests.
5. Attach the persistent volume at `/data` before the first signup; the
   production template places SQLite, graph memory, uploaded inputs, and
   artifacts there. Run ClamAV and Qdrant as private Railway services only.

Before inviting testers, verify `https://api.clannon.com/health`, signup/login
from `https://clannon.com`, authenticated `/auth/me`, and an authenticated SSE
run in a real browser. The stored session cookie must be Secure, HttpOnly, and
domain-scoped to `.clannon.com`.

Production replacements tracked: Supabase (swap `auth.py`), Postgres for the
current SQLite store, Stripe (`/billing/*`), Redis token metering (`/usage`).
