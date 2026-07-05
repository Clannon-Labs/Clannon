# Clannon API server (Vraksha engine)

The FastAPI surface the Clannon frontend talks to. It wraps the existing
pipeline (`core.pipeline.ACTIVE_STAGES`) **without modifying it** and serves
the contract below. This file is the single source of truth for the
backend↔frontend contract — when you add or change an endpoint, update the
table here.

```bash
# from backend/ (with the venv activated) — the dir that holds api/, main.py,
# models.yaml and .env.local; running from elsewhere can't resolve api.app or
# the top-level core/foundation/security imports
uvicorn api.app:app --port 8000 --reload
```

To reach the server from another device on the LAN (e.g. test the frontend on
a phone), use the launcher. It frees the port if a previous run is still on it,
detects this machine's LAN IP, wires `FRONTEND_ORIGIN` for CORS, and binds to
all interfaces — no env vars to remember, safe to re-run:

```bash
./dev.sh          # from backend/  (venv must exist at .venv/)
```

Equivalent by hand (`<LAN-IP>` = `hostname -I | awk '{print $1}'`):

```bash
FRONTEND_ORIGIN=http://<LAN-IP>:3000 \
  uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
# if ufw is active, open the port once: sudo ufw allow 8000/tcp
```

`--host 0.0.0.0` is the part that matters — the default binds to `127.0.0.1`
and is invisible off-box. `FRONTEND_ORIGIN` must exactly match the frontend's
LAN origin or CORS rejects every request (see the table below).

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
| `app.py` | All routes, CORS, request/response models. |
| `auth.py` | Users + sessions + the SQLite data layer (projects, wiki, model prefs — every query lives here, never in the routes). Scrypt, httpOnly cookies. The dev stand-in for Supabase — swap this one module when Supabase lands. |
| `runs.py` | Run store, pipeline execution, decision-log observation, SSE streaming. |
| `config.py` | The `/config` payload (plans/features/limits) + server settings. |

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
| `/projects` | POST | `{name, color?, seedFacts?}` | created `Project`. `seedFacts` (optional markdown): also creates a first WIKI entry in the project titled `Client: <name> — context` (the onboarding "tell Clannon about this client" step) |
| `/projects/:id` | PATCH | `{name}` | renamed `Project` (404 if not the caller's) |
| `/projects/:id` | DELETE | — | `204` cascade: deletes the project AND its runs (+ their stored files) AND its wiki/memory scope. Owner-scoped + idempotent (same semantics as `DELETE /sessions/:id`). The learned cross-session memory (Qdrant tiers) is retained |
| `/runs` | GET | `?projectId=<id>` (optional) | `RunSummary[]` — filtered to one project when `projectId` is given, all of the user's runs when omitted. Each `RunSummary`/`Run` carries an optional `projectId` |
| `/runs` | POST | `multipart/form-data`: `brief` (text) + optional `files` (input files) + optional `models` (JSON object `role -> model`, per-session model choices) + optional `projectId` (the run is created in that project; an unknown/other-user project is a 422) | `{id}`, starts the pipeline in the background. Each uploaded file is malware-scanned at the boundary (ClamAV/YARA) and seeded into the expert workspace with its original bytes — clean files are NOT redacted; a malicious/unsupported/oversized file is a 422. File scope: text, PDF, image, audio, video; max 10. `models` overrides the user's workspace defaults for this run only (422 on an unknown/locked role or an unavailable model) |
| `/runs/:id` | GET | — | full `Run` (decisionLog, experts, **message**, report, sources, artifacts, inputs, feedbackRating, parentRunId, sessionId, blockStage). `message` = the orchestrator's conversational chat bubble (the agent talking to the user); `report`/`artifacts` = the deliverable. A turn may have `message` only (pure conversation), both, or `report` only. |
| `/runs/:id/artifacts/:name` | GET | — | the bytes of one delivered artifact (`Content-Disposition: attachment`). 404 unless the run actually published a file by that name — the run's own artifact list is the auth boundary |
| `/runs/:id/stream` | GET (SSE) | — | `data:` frames, each one JSON `RunEvent`: `status` / `log` / `expert` / `message_delta` / `message_done` / `report_delta` / `report_done` / `sources` / `usage`. `message_delta` is the orchestrator's CONVERSATIONAL voice streamed live (it can talk *while experts run*) and is independent of `report_delta` (the deliverable) and `log` (structured ticks); `message_done` closes it. `sources` carries the grounded-search `Source[]` backing a delivered run and is emitted once, just before the report streams (empty when the run ran no grounded search). Terminal `status` values: `delivered` / `blocked` / `failed` / `cancelled` — the stream closes after a terminal status, and a reconnect replays the buffered sequence (incl. the message stream) ending in it |
| `/runs/:id/cancel` | POST | — | Cooperatively stop an in-flight run. `204` if already terminal (idempotent); otherwise `200 {status:"cancelling"}` and the authoritative `cancelled` arrives over the SSE stream. Ownership-scoped (404 if not the caller's run). Cancel ≠ delete — the run stays in history with status `cancelled` (distinct from `failed`/`blocked`). Tokens spent up to the stop are charged (usage-based) |
| `/runs/:id/feedback` | POST | `{rating: "up"\|"down"\|null, comment?}` | 204; thumbs rating on a delivered run |
| `/runs/:id/followup` | POST | `multipart/form-data`: `brief` (text) + optional `files` + optional `models` | `{id}`, the next turn of the same session — inherits `sessionId` (`parentRunId` set). Carries input files AND per-session `models` exactly like `POST /runs`; the follow-up run's `inputs` lists the files. The **whole session** is replayed to the orchestrator as real chat history (`message_history`) — every prior turn's brief, conversational message, and report, plus a note of any files each turn attached (trimmed only when the session grows huge, oldest-first). Files uploaded in ANY earlier turn are **persisted and re-seeded** into the expert workspace, so the agent can still read a file referenced several turns later. Only the new brief is sanitized/verified. The follow-up **inherits the parent's `projectId`** (no `projectId` on this endpoint). |
| `/runs/:id/thread` | GET | — | `Run[]` — every turn of this run's session, oldest first (the conversation) |
| `/runs/:id/audit` | GET | — | Security-decision audit records for this run, owner-scoped. `[]` when the run was not blocked by any security gate or predates the audit trail. `404` when the run is not the caller's. Each record: `{id, traceId, sessionId, blockCode, threatLevel, origin, reason, blockedAt}` — `blockedAt` is ISO 8601 UTC; `blockCode` is the `BlockReason` enum value; `origin` is the blocking gate (`sanitizer`, `verifier`, `filter`); `reason` is the human-readable block explanation, or `null` if the gate did not produce one. |
| `/sessions/:id` | DELETE | — | Permanently delete a whole conversation (every turn in the session). Owner-scoped and idempotent: `204` whether it deleted turns or there was nothing to delete (a session that isn't the caller's is a no-op `204`, never revealed). Removes the conversation + its turns, and purges its stored files (uploaded inputs AND output artifacts) from disk; the assistant's learned cross-session memory is retained. Any in-flight run in the session is cancelled. |
| `/memory` | GET | `?projectId=<id>` (optional) | `MemoryEntry[]` (wiki from SQLite + episodic from runs), each with an optional `projectId`. Filtered to one project when `projectId` is given, all of the user's memory when omitted. (Scopes the user-controlled **wiki** tier + the episodic list; project-scoping the learned Qdrant tiers is a memory-workstream follow-up) |
| `/memory/hydration-preview` | GET | `?brief=<text>&projectId=<id>` (projectId optional) | `(MemoryEntry & {score: number})[]` — a read-only DRY-RUN of `MemoryPort.hydrate` for a draft brief: what the run would actually carry, ranked by the Manager's real trust+similarity+recency ordering, capped at 8. Same `user_id` scoping as hydrate (same door, not a new access path). Wiki hits carry their real entry id/title; learned-tier hits get `preview_<n>` ids + derived titles. Best-effort: brief `<3` chars, degraded memory, or a memory fault ⇒ `[]`, never a 5xx. Debounce client-side (~1/s). |
| `/memory` | POST | `{tier:"wiki", title, content, projectId?}` | created entry (only wiki is user-writable; an unknown/other-user `projectId` is a 422) |
| `/memory/:id` | PUT / DELETE | entry / — | updated entry / 204. DELETE works for a WIKI entry (id `m_…`) AND an EPISODIC one (id `<run_id>_m<i>`) — deleting an episodic recollection drops it from its run (the "that's outdated" action), owner-scoped, 404 if neither matches. (Wiki UPLOAD `/memory/upload` takes `projectId` as a form field OR a `?projectId=` query param.) |
| `/usage` | GET | — | `UsageSummary` `{periodStart, periodEnd, budget, used, byDay[]}` — `used` is the REAL metered spend (sum of `run.tokensUsed` over a trailing 30-day window), `budget` is the user's plan budget. `run.tokensUsed` reflects each run's actual tokens (every model call in the turn, charged on delivered/blocked/cancelled alike). Redis-atomic budget enforcement (decrement + hard stop) lands separately. |
| `/settings/models` | GET / PUT | — / `{layer, model}` | `RoleModelConfig[]` / 204. One entry PER ROLE: 5 selectable (orchestrator, research, planner, code, media_expert) + verifier/filter read-only. Each entry carries `model` (the user's workspace default or the system default), `default`, `options`, `locked`, and `experts` (which experts the role drives). Defaults are derived from `models.yaml` (Claude for reasoning, Gemini for media). PUT sets the per-user WORKSPACE default for a role (403 locked, 422 model not in options). Per-SESSION overrides go on the run POST via `models`. |
| `/billing/checkout` `/billing/portal` | POST | — | 501 until Stripe |

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

## Deployment (Railway + Vercel)

1. Deploy this repo to Railway: start command
   `uvicorn api.app:app --host 0.0.0.0 --port $PORT`, set `FRONTEND_ORIGIN`
   to the Vercel URL, `SERVER_COOKIE_SECURE=1`, and the provider API keys.
2. On Vercel, set the frontend env: `NEXT_PUBLIC_API_MODE=http`,
   `NEXT_PUBLIC_API_BASE_URL=https://<railway-app>.up.railway.app`,
   `NEXT_PUBLIC_SITE_URL=https://<your-domain>`.
3. That's the whole wiring — no code changes on either side.

Production replacements tracked: Supabase (swap `auth.py`), Postgres for the
run store (today in-memory — runs vanish on restart), Stripe (`/billing/*`),
Redis token metering (`/usage`).
