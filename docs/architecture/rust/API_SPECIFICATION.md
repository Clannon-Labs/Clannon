# API specification — the 38 routes Rust must serve

**Purpose:** you are building the Rust API surface and need to know what each route
is for. This is reference, not rationale — the "why" lives in `DECISIONS.md`.

**Source of truth is the code**, not this file: `backend/api/app.py` (33 routes),
`billing.py` (4), `run_revision.py` (1). Verified against them 2026-08-02.

> **Correction to an earlier count:** I said 33 routes in the structure proposal. It is
> **38** — I had deduplicated by path and lost the routes that share a path with a
> different method (`GET`/`POST /memory`, `GET`/`PUT /settings/models`, and others).

## 0. Rules that apply to every route

| Rule | Detail |
|---|---|
| Auth | HTTP-only cookie, `SameSite=Lax`, set by `/auth/login` and `/auth/signup`. 30 of 38 routes require it. |
| Ownership | Every resource is fetched **scoped by `user.id`**. Never "fetch then check". |
| Non-disclosure | A resource owned by someone else returns **404**, never 403. A foreign run must be indistinguishable from a nonexistent one. |
| Errors | `HTTPException(status, "human sentence")` → `{"detail": "..."}`. Messages are user-facing prose. |
| Status codes in use | 401 auth · 403 forbidden · 404 not-found/non-disclosure · 409 conflict · 422 validation · 429 rate limit · 503 dependency down |

**The 8 unauthenticated routes:** `/health`, `/ready`, `/config`,
`POST /auth/signup`, `POST /auth/login`, `POST /auth/logout`,
`GET /auth/oauth/{provider}`, and `POST /billing/mock/confirm`.

---

## 1. Full route table

### Meta — 3

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | no | Process is up. Sync, no I/O. |
| GET | `/ready` | no | Dependencies up (Qdrant, embeddings, DB). Returns `JSONResponse` so it can be 503. |
| GET | `/config` | no | Public client config — limits, feature flags. **Never leaks `config/` business values.** |

### Auth — 5

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/auth/signup` | no | Create account, set cookie. |
| POST | `/auth/login` | no | Set cookie. |
| POST | `/auth/logout` | no | Delete cookie (`path=/`, `domain=COOKIE_DOMAIN`). |
| GET | `/auth/me` | yes | Current user. The frontend's session probe — 401 when absent. |
| GET | `/auth/oauth/{provider}` | no | `RedirectResponse` to the provider. |

### Projects & sessions — 5

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/projects` | yes | User's projects. |
| POST | `/projects` | yes | Create. |
| PATCH | `/projects/{project_id}` | yes | Rename. |
| DELETE | `/projects/{project_id}` | yes | Remove. |
| DELETE | `/sessions/{session_id}` | yes | Delete a conversation. |

### Runs — 12 (the core)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/runs` | yes | Summaries, newest first. Optional `?projectId=` filter; omitted = all. |
| POST | `/runs` | yes | **Create and start.** `multipart/form-data`. → **201** `{"id": "..."}` |
| GET | `/runs/{id}` | yes | Full run JSON (`run.full_json()`). |
| GET | `/runs/{id}/stream` | yes | **SSE.** See §2. |
| GET | `/runs/{id}/thread` | yes | Conversation turns for the effective thread. |
| GET | `/runs/{id}/decisions` | yes | Decision log — **events, never payloads**. |
| GET | `/runs/{id}/audit` | yes | Durable audit mirror. |
| GET | `/runs/{id}/artifacts/{name}` | yes | Download a generated file. |
| POST | `/runs/{id}/cancel` | yes | Cooperative stop. See §3. |
| POST | `/runs/{id}/followup` | yes | Continue the conversation. |
| POST | `/runs/{id}/revise` | yes | Edit a turn **destructively**. See §4. |
| POST | `/runs/{id}/feedback` | yes | `{rating: "up"\|"down"\|null, comment?}` → **204** |
| GET | `/runs/archive` | yes | Archived runs. |

### Memory — 6

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/memory` | yes | Entries with provenance. **Plan-tier filtered server-side.** |
| POST | `/memory` | yes | Create a wiki entry (user-authored tier only). |
| PUT | `/memory/{entry_id}` | yes | Update a wiki entry. |
| DELETE | `/memory/{entry_id}` | yes | Real deletion. Foreign id → 404, indistinguishable from unknown. |
| GET | `/memory/hydration-preview` | yes | What memory *would* be selected for a query. Best-effort: any failure returns `[]`, never an error. |
| POST | `/memory/upload` | yes | Upload a file into memory. |

### Settings, usage, billing — 7

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/settings/models` | yes | Available models for this plan. |
| PUT | `/settings/models` | yes | Set preferred model. → 204 |
| GET | `/usage` | yes | Token/cost usage incl. **cache read/write tokens**. |
| POST | `/billing/checkout` | yes | Start checkout. |
| GET | `/billing/checkouts/{checkout_id}` | yes | Checkout status. |
| POST | `/billing/portal` | yes | Billing portal link. |
| POST | `/billing/mock/confirm` | no | Mock settlement. **Dev/alpha only — must be disabled in production.** |

---

## 2. `GET /runs/{id}/stream` — the hard one

SSE. `text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`.

**Frames carry no SSE event name.** Every frame is `data: {json}\n\n`, and the JSON
carries a `"type"` field. Do not "improve" this into named events — see the contract
lock below.

### Event types

| `type` | Meaning |
|---|---|
| `status` | Lifecycle transition |
| `log` | Progress line |
| `expert` | Expert started/finished |
| `verification` | Filter/groundedness verdict |
| `message_delta` | Chat answer chunk |
| `report_delta` | Report chunk |
| `report_done` | Report complete |

### Replay-then-live — get this exactly right

1. Snapshot `run.events` into `replay`.
2. Create the subscriber queue and register it.
3. **No `await` between 1 and 2.** That is what stops an event landing in both the
   replay and the live queue, or in neither.
4. Yield all replayed frames.
5. If the run is terminal — and not the legacy `delivered`-with-no-report case — **return**. A reconnect to a finished run must close, not hang.
6. Otherwise loop on the queue; a `None` sentinel ends the stream.
7. `finally`: remove the subscriber.

**Terminal ordering is a pinned invariant:** `report_done` is emitted strictly
**before** `status: delivered` (`tests/sse_terminal_order.py`).

> **CONTRACT LOCK.** `backend/tests/sse_contract_drift.py:479` fails on any SSE event
> the frontend has not declared, and `:518` blocks a new terminal `partial` status.
> That benchmark is what keeps **CB6 — the only Critical benchmark that passes** —
> green. Rust must satisfy it unchanged. Do not add an event type to unblock yourself.

---

## 3. Semantics you cannot infer from the signature

### `POST /runs` (multipart)

| Field | Type | Notes |
|---|---|---|
| `brief` | Form, required | `briefMinChars` ≤ len ≤ `BRIEF_MAX_CHARS`; under min → 422 "Say a little more to get started." |
| `files` | File[] | Malware pre-gate only; **original bytes preserved**, never redacted |
| `models` | Form | Per-session model override |
| `projectId` | Form | Required in practice via `_require_project` |

Order is load-bearing: validate → resolve project → admit uploads → parse models →
**`billing.admit_run`** → create → **register the task before any further `await`**.
Once the store exposes the run, every cancellation path needs a live task to stop.

### `POST /runs/{id}/cancel`

| Outcome | Response |
|---|---|
| Not owned / missing | 404 |
| Already terminal | **204** — idempotent |
| Live run | 200 `{"status": "cancelling"｜"cancelled"｜"failed"}` |

The 200 body is **informational**. The authoritative `cancelled` arrives over SSE.
Cancel ≠ delete: the run stays in history.

### `POST /runs/{id}/revise` — destructive, and deliberately so

Keeps the target's `sessionId`/`projectId`. The old prompt/response **and every later
turn** become user-inaccessible (404) and vanish from `/runs`, `/thread`, model
conversation, recall transcript, and inherited-file reseeding. Superseded rows survive
internally for spent-token accounting, saved memory, and audit provenance — the marker
must **never** enter public JSON.

### `GET /memory`

Plan tiers are derived from canonical config and **enforced server-side**. This was a
real breach: a free account received full paid wiki content because the lock was
frontend-only. Unknown plan → fail closed.

### `GET /memory/hydration-preview`

Best-effort. Any exception → `[]`. Degraded package → `[]`. Never an error surface.

---

## 4. What Rust must not change

| Thing | Why |
|---|---|
| SSE event vocabulary | `sse_contract_drift.py` — CB6 depends on it |
| `report_done` before `status: delivered` | `sse_terminal_order.py` |
| 404-not-403 for foreign resources | Non-disclosure invariant |
| Cookie name / `SameSite=Lax` / domain | Live browser sessions |
| Decision log carries events, not payloads | The log streams **before** the output filter; payloads there bypass it |
| `POST /billing/mock/confirm` unauthenticated | Only acceptable because it is dev-only — **disable in production** |

---

## 5. Route → Rust module

| Group | Suggested module | Depends on |
|---|---|---|
| meta | `api::meta` | readiness probes |
| auth | `api::auth` | session store, cookies |
| projects/sessions | `api::projects` | persistence |
| runs | `api::runs` | pipeline, SSE hub, budget admission |
| memory | `api::memory` | MemoryPort, plan tiers |
| settings/usage | `api::settings` | registry, usage store |
| billing | `api::billing` | budget, settlement |

`api::runs` is the largest and the only one with a live streaming surface — build it
last, after the pipeline it drives exists.
