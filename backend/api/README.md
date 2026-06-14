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

## Environment

Loads `.env` then `.env.local` from `backend/` (the working directory, same as
`main.py`), so the pipeline gets its provider keys. Server-specific variables:

| Variable | Default | What it does |
|---|---|---|
| `FRONTEND_ORIGIN` | `http://localhost:3000` | CORS allow-origin + where OAuth errors redirect. Must exactly match the frontend's origin (scheme + host + port). |
| `SERVER_DEFAULT_PLAN` | `free` | Plan for new signups. Use `pro` in local dev to unlock all memory tiers. |
| `SERVER_COOKIE_SECURE` | `0` | Set `1` in production (HTTPS) so the session cookie is Secure. |
| `SERVER_DB_PATH` | `api/data/clannon.db` | SQLite location (users, sessions, wiki, model prefs). |

## Module map

| File | Owns |
|---|---|
| `app.py` | All routes, CORS, request/response models. |
| `auth.py` | Users + sessions (SQLite, scrypt, httpOnly cookies). The dev stand-in for Supabase — swap this one module when Supabase lands. |
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
| `/runs` | GET | — | `RunSummary[]` |
| `/runs` | POST | `multipart/form-data`: `brief` (text) + optional `files` (input files) | `{id}`, starts the pipeline in the background. Each uploaded file is malware-scanned at the boundary (ClamAV/YARA) and seeded into the expert workspace with its original bytes — clean files are NOT redacted; a malicious/unsupported/oversized file is a 422. Scope: text-family files + PDF, max 10 |
| `/runs/:id` | GET | — | full `Run` (decisionLog, experts, report, sources, artifacts, inputs, feedbackRating, parentRunId, sessionId, blockStage) |
| `/runs/:id/artifacts/:name` | GET | — | the bytes of one delivered artifact (`Content-Disposition: attachment`). 404 unless the run actually published a file by that name — the run's own artifact list is the auth boundary |
| `/runs/:id/stream` | GET (SSE) | — | `data:` frames, each one JSON `RunEvent`: `status` / `log` / `expert` / `report_delta` / `report_done` / `usage` |
| `/runs/:id/feedback` | POST | `{rating: "up"\|"down"\|null, comment?}` | 204; thumbs rating on a delivered run |
| `/runs/:id/followup` | POST | `{brief}` | `{id}`, the next turn of the same session — inherits `sessionId` (`parentRunId` set). Prior turns are replayed to the orchestrator as real chat history (`message_history`), so only the new brief is sanitized/verified and the model genuinely continues the conversation. |
| `/runs/:id/thread` | GET | — | `Run[]` — every turn of this run's session, oldest first (the conversation) |
| `/memory` | GET | — | `MemoryEntry[]` (wiki from SQLite + episodic from runs) |
| `/memory` | POST | `{tier:"wiki", title, content}` | created entry (only wiki is user-writable) |
| `/memory/:id` | PUT / DELETE | entry / — | updated entry / 204 |
| `/usage` | GET | — | `UsageSummary` (plan budget; metering arrives with Redis budgets) |
| `/settings/models` | GET / PUT | — / `{layer, model}` | `LayerModelConfig[]` / 204 (stored per-user; pipeline wiring TODO) |
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
