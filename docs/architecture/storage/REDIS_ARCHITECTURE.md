# Clannon Redis Architecture (Production)

> **Purpose:** What Redis does in Clannon and why — the four jobs, the
> correctness decisions, and the failure behavior.
> **Scope:** Token budgets, hot session state, background-job tracking, rate
> limiting, the connection model, and the Redis↔Postgres split.
> **Authority level:** Tier 5 (Subsystem). Inherits
> [../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md) and the Invariants.
> **Related:** [README.md](README.md) · [../memory/](../memory/) ·
> [../../decisions/accepted/0004-redis-enforces-postgres-truths-budget.md](../../decisions/accepted/0004-redis-enforces-postgres-truths-budget.md)

> Status: design reference for the post-Macondo production phase.
> This document describes **what Redis does in Clannon and why**, the decisions
> behind each use, and the failure behavior. Where a decision depends on code
> that only you can see, it is marked **[NEEDS YOUR CODE]** instead of guessed.

---

## 1. What Redis is (one paragraph, no syntax)

Redis is a separate in-memory data server. Your FastAPI backend talks to it over
the network through a client library. It is not a library you "just import" — the
library is only the phone line; the Redis server is the thing on the other end
that actually holds the data. In local dev you run that server yourself (Docker).
In production your architecture uses **Upstash Redis** as the managed server. The
same Python client code points at either one; only the connection URL changes.

Redis holds data in RAM, which is why it is fast and why it is used for the
"hot" and "real-time" jobs in Clannon — not for anything that must survive
forever. Postgres is the durable source of truth; Redis is the fast layer in
front of it.

---

## 2. The four jobs Redis does in Clannon

Your system architecture assigns Redis four distinct responsibilities. They are
unrelated to each other except that they all need a fast shared store. Keeping
them mentally separate is the most important thing in this whole document.

| # | Job | Where in arch doc | Durability need | Can it be lost? |
|---|-----|-------------------|-----------------|-----------------|
| 1 | Token budget enforcement | "Token Budget System" | Mirrored to Postgres | No — must reconcile |
| 2 | Hot session state | "Session Continuity" | Rebuildable from memory tiers | Yes — degrades, not breaks |
| 3 | Background job tracking | "Background Jobs And Async Work" | Transient | Yes — job can be re-run |
| 4 | Rate limiting | "Intake" | Transient | Yes — fail open or closed by policy |

Each job gets its own **key namespace** (a prefix on the key name) so they never
collide and so you can reason about, expire, or flush one job without touching
the others.

---

## 3. Decision: one Redis instance, namespaced — not four instances

You use a **single Redis instance** for all four jobs, separated by key prefix:

```
budget:{user_id}:{billing_period}      -> job 1
session:{session_id}                   -> job 2
job:{job_id}                           -> job 3
ratelimit:{scope}:{identifier}         -> job 4
```

Reasoning:

- Your scale (solo founder, first paying users) does not justify the operational
  cost of multiple instances.
- Upstash bills per request, not per instance, so splitting saves nothing.
- Namespacing gives you the isolation benefit (clear ownership, targeted
  expiry) without the infrastructure cost.

Revisit only if one job's traffic starts to starve another, which will not
happen at your stage.

---

## 4. Job 1 — Token budget enforcement (the one that must be correct)

This is the only Redis job where a bug costs you money or wrongly blocks a paying
user. It deserves the most care.

### 4.1 What the arch doc requires

- Redis holds **remaining budget per user per billing period**.
- Every LLM call **atomically decrements** before the call proceeds.
- If the budget is exhausted, the call is **blocked** and the user notified.
- Postgres is the **durable source of truth**, synced asynchronously from Redis.
- Resets are triggered by Stripe `invoice.paid` webhooks, updating both stores.

### 4.2 The decision that matters: check-then-decrement must be atomic

There is a trap here. The obvious approach — read the budget, check if it's
enough in Python, then decrement — is **wrong** under concurrency. Two LLM calls
for the same user finishing at the same moment can both read "5000 left," both
decide "enough," and both decrement, driving the budget negative or letting
through a call that should have been blocked. This is a classic lost-update race.

A plain atomic `DECRBY` does not fix it either: `DECRBY` is atomic, but it
**cannot refuse** to go negative. It will happily decrement 5000 by 8000 and
leave you at −3000. By the time your code reads the negative number and reacts,
the expensive LLM call may already be in flight.

**Decision:** the check ("is there enough?") and the decrement ("take it") must
happen as **one indivisible operation on the Redis server**. The correct tool is
a small **Lua script** run via `EVAL`. Redis executes a Lua script atomically —
nothing else runs in between — so the script can read the balance, compare it to
the requested amount, and only decrement if sufficient, returning a clear
allow/deny result. This is the standard pattern for "counter with a limit," and
it is the only correct one for budgets.

Confirmed: **Upstash supports Lua scripting**, so this pattern works identically
in local dev and production.

### 4.3 The reservation problem (decision you must make consciously)

A subtle issue your arch doc implies but does not resolve: **you don't know the
exact token cost of an LLM call until after it finishes.** You decrement *before*
the call ("decrement Redis atomically before the call proceeds"), but the real
cost is known only after.

Two honest options:

- **Estimate-then-reconcile (recommended):** before the call, reserve an
  *estimated* cost (e.g. based on input size + a max-output assumption). After
  the call, adjust by the difference between estimate and actual. This prevents
  a user from starting a huge call with almost no budget left.
- **Charge-after-only:** let the call run, then decrement by the real amount.
  Simpler, but a user at 100 tokens remaining could trigger a 50k-token call.
  Acceptable only if you accept small overruns as a cost of doing business.

This is a **product/economics decision, not a technical one** — it trades margin
protection against implementation complexity. Pick deliberately. The doc's 35–40%
margin target leans toward estimate-then-reconcile.

### 4.4 Redis ↔ Postgres split

- **Redis** answers the real-time question "can this call proceed?" in
  single-digit milliseconds. It is the *enforcement* store.
- **Postgres** is the *truth* store: billing, reset history, audit. It does not
  sit in the hot path of every LLM call.
- Sync is **async** Redis → Postgres. The arch doc is explicit that Postgres is
  "synced asynchronously from Redis," so a periodic/triggered flush writes the
  authoritative remaining balance to Postgres. Postgres never needs to be
  consulted per-call.

**Failure stance:** if Redis is unreachable on a budget check, you must choose
**fail-closed** (block the call — protects margin, frustrates a paying user) or
**fail-open** (allow it — protects UX, risks free usage). For a paid product
with a margin target, **fail-closed with a clear "service degraded" message** is
the defensible default. State this explicitly in code; do not let it be
accidental.

### 4.5 Reset flow

Stripe `invoice.paid` webhook → your webhook handler →
1. write the fresh full budget to Redis for the new `{billing_period}`,
2. write the same to Postgres,
3. (optional) let the old period's key expire naturally.

Keying budget by `{user_id}:{billing_period}` means a reset is just writing a new
key, not mutating the old one — cleaner audit trail and no race with in-flight
decrements on the boundary.

**[PARTIAL — go-live gate]** Billing now uses a fixed anniversary period anchored to
signup or latest confirmed plan payment (`api/billing.py::billing_period`). Redis
reservations preserve the exact period that granted each hold, so a call crossing a
boundary settles the old key. Production broker construction still defaults to a UTC
calendar month and seeding is not wired; both must consume the API's anniversary-period
identity before enforcement can turn on. Get this wrong and resets drift from invoices.

---

## 5. Job 2 — Hot session state (continuity)

### 5.1 What the arch doc requires

- Hot session state lives in Redis "while the model context is healthy."
- Session state is **platform-agnostic** — start on web, get result via
  messaging, no discontinuity.
- When context pressure crosses a threshold, Clannon summarizes, writes durable
  context to memory tiers, drops ephemeral state, and silently starts a fresh
  model session.
- The Memory Manager rebuilds hydration for the new session.

### 5.2 The key decision: Redis session state is a *cache*, not the *truth*

This is the opposite stance from Job 1. Session state in Redis is **disposable**.
The durable record of what happened lives in the **memory tiers** (episodic,
semantic, etc., via the MemoryPort). Redis holds only the *hot working copy* so
the orchestrator doesn't re-hydrate from scratch on every turn.

Why this matters: it means losing Redis session data **degrades** the experience
(a rehydration cost) but does not **destroy** anything. The arch doc's whole
continuity model — summarize, write to memory, drop ephemeral state — only works
if Redis is explicitly the throwaway layer. Treat it as truth and you will fight
the architecture.

### 5.3 What actually goes in the session key

Per the arch doc's hydration list, the hot session blob holds: current task
state, recent high-signal turns, and pointers/cached copies of the
Memory-Manager-built hydration package (relevant wiki, semantic, episodic,
procedural). It does **not** hold full transcript replay — the doc forbids that.

**Expiry:** session keys should carry a TTL (time-to-live) so abandoned sessions
self-clean. The TTL length is a product decision (how long is a session "warm"?).

**[NEEDS YOUR CODE]** The exact shape of your session object — what your Flow
`context` carries, what the orchestrator needs on each turn — determines the
serialized structure stored here. I won't invent a schema; it must mirror your
actual context contract in `foundation`.

### 5.4 Cross-platform continuity

Because session state is keyed by `session_id` (not by platform), the same hot
state is reachable whether the user is on web or messaging. This is already how
your arch doc describes it; Redis is simply the shared place that makes
"start on web, finish on messaging" possible without a per-platform store.

---

## 6. Job 3 — Background job tracking

### 6.1 What the arch doc requires

- Long tasks (deep research, large docs, batch media, memory consolidation,
  complex multi-expert reports) are routed to background jobs.
- Each job writes state to Redis under a **job ID**.
- The user gets an immediate ack + a progress handle.
- The dashboard polls or receives a push on completion.
- Results surface through the same delivery layer as sync responses.

### 6.2 The decision: Redis as job-status store, and the question of a queue

Two separate things are bundled in "background jobs," and you should not conflate
them:

1. **Job status/state** — "is job X queued / running / done / failed, and what's
   its progress?" Redis holds this. A key per `job:{job_id}` with status and
   progress fields. This is clearly in scope and Redis is the right tool.

2. **Job execution / queueing** — *what actually runs the work* off the request
   thread. The arch doc says jobs are "routed to background jobs" but does not
   name the worker mechanism. This is an **open architectural decision**:
   - Redis can also back a real task queue (via a library like RQ or Celery with
     a Redis broker, or Arq for async). Same instance, different use.
   - Or you use a separate mechanism and Redis only tracks *status*.

   **[NEEDS YOUR CODE / DECISION]** I will not guess which you intend. Your arch
   doc specifies the status store but not the executor. Decide explicitly:
   *does Redis also broker the work, or just track it?* This affects whether you
   add a queue library and a worker process to your Railway deployment.

### 6.3 Result delivery

The arch doc says the dashboard "polls or receives a push notification." Redis
job state supports both: polling reads the `job:{job_id}` key; push can be driven
by Redis **pub/sub** (a publish/subscribe channel that notifies subscribers when
a job completes) if you want server-push rather than client-poll. Pub/sub is
optional and can come later — polling is fine for first paying users.

---

## 7. Job 4 — Rate limiting (intake)

### 7.1 What the arch doc requires

The Intake stage owns "request rate limiting." Separately, the demo system does
**IP-based rate limiting** at its entry point (but the demo is isolated from the
real pipeline, so its limiter is conceptually a fifth, walled-off user of Redis —
or even a separate store).

### 7.2 The decision: counter-with-expiry, scoped deliberately

Rate limiting in Redis is a counter that auto-expires over a time window. The
core pattern: increment a counter for `{scope}:{identifier}`; if it exceeds the
limit within the window, reject; let the key expire to reset the window.

The decisions you must make:

- **Scope:** per-user? per-IP? per-endpoint? The arch doc says intake rate-limits
  *requests*; for authenticated traffic this should be **per `user_id`**, because
  identity is already established at the authenticated entry point (your security
  model is explicit that `user_id` is set once at entry and is authoritative).
  For the demo, it's per-IP because there's no signup.
- **Algorithm:** a fixed-window counter is simplest and fine to start. Sliding
  window is more precise but more complex. Start fixed, upgrade if abuse appears.
- **Fail stance:** if Redis is down, does intake fail-open (allow) or fail-closed
  (reject)? For rate limiting specifically, **fail-open** is usually right — you
  don't want a Redis blip to take down all intake — but that is a security
  tradeoff to make consciously.

### 7.3 Don't hand-roll if a vetted limiter exists

Atomicity matters for rate limiters too (same race-condition family as budgets).
A correct limiter uses a server-side atomic step. If you adopt a maintained
limiter implementation, prefer it over hand-writing the window logic — the edge
cases (window boundaries, atomic increment+expire) are easy to get subtly wrong.
**[DECISION]** whether to use a library or hand-roll a Lua-based limiter.

---

## 8. Connection model — the one production fact that changes your code

Your backend is **FastAPI on Railway** — a persistent, long-running server that
*can* hold TCP connections. This determines the client choice:

- **Use the standard `redis-py` client over TCP** (its async interface,
  `redis.asyncio`, since your stack is async). This supports connection pooling,
  pipelining, and Lua `EVAL` — everything jobs 1–4 need.
- **Do NOT use Upstash's HTTP/REST client** here. The REST API exists for
  serverless/edge runtimes (Cloudflare Workers, Vercel Edge) that *cannot* hold
  TCP connections. Railway can, so TCP is faster and more capable. The REST path
  would only matter if some piece of Clannon ran on an edge runtime.

Upstash speaks the normal Redis TCP protocol too, so the standard client
connects to it directly. **Same `redis-py` code, local and production; only the
connection URL (and TLS) differ.** Local uses `redis://localhost:...`; Upstash
uses a TLS `rediss://...` URL with a token, supplied via environment variable.

### 8.1 One client, created at app startup

Create a single async Redis client when FastAPI starts and reuse it everywhere
(it pools connections internally). Do not open a connection per request. This is
a hard rule — per-request connections exhaust limits under load.

**[NEEDS YOUR CODE]** Whether you already have a Redis client module, and where
your app's lifespan/startup wiring lives, determines exactly where this singleton
is created and how stages reach it (dependency injection vs app state vs a
module-level accessor). I can't place it correctly without seeing your FastAPI
entry point and your `foundation`/`core` layout.

---

## 9. Where Redis fits the layering rules

Your arch doc is strict that `foundation` stays "framework-light and
provider-neutral" and must not own provider SDK calls. Redis is a provider
dependency, so by the same logic that confines the LLM SDK to `core/llm`:

- The **Redis client and the raw command calls should be confined to a single
  owned module** (e.g. a `core/redis` or infrastructure layer), not scattered
  across stages — mirroring how `framework.py` is the single entry point for the
  LLM SDK.
- Stages (intake, orchestrator, token-budget logic) call **your** functions
  (`reserve_budget`, `get_session`, `set_job_status`, `check_rate_limit`), never
  raw `redis-py` directly. This keeps Redis swappable and auditable from one
  place, exactly like the framework adapter rule.

This is the same architectural principle you already applied to Pydantic AI and
to the Qdrant Memory Manager boundary: **provider SDKs live behind a Clannon-owned
seam.** Redis should not be an exception.

**[DECISION]** the exact module name and whether budget/session/job/ratelimit
each get their own sub-module behind that seam. Recommended: one connection
module + four small service modules (one per job), so the four concerns stay
separate above the shared client.

---

## 10. Security notes specific to Redis

- **No tenant leakage via keys.** Every user-scoped key embeds `user_id` from the
  authenticated Flow context — never from request content or model output. This
  is the same invariant your security model states for memory and tools; it
  applies identically to Redis keys. A budget or session key built from anything
  other than the authenticated identity is the Redis equivalent of an unscoped
  query.
- **Upstash connection is TLS** (`rediss://`) and token-authenticated. Keep the
  URL/token in environment variables, never in code.
- **Redis is not your audit log.** Anything you must be able to prove later
  (billing, usage) lives durably in Postgres. Redis can be flushed without losing
  legally/financially meaningful state.

---

## 11. What requires your actual code before implementing (summary)

These are the points above where guessing would introduce bugs. Bring the
relevant code and these resolve quickly:

1. **Billing period definition** (§4.5) — must match your Stripe billing anchor.
2. **Session object schema** (§5.3) — must mirror your Flow `context` contract.
3. **Background executor** (§6.2) — does Redis broker work or only track it?
4. **Rate-limit library vs hand-roll** (§7.3) and fail-open/closed (§7.2).
5. **Client singleton placement** (§8.1) — depends on your FastAPI startup wiring.
6. **Redis seam module layout** (§9) — depends on your `core`/`foundation` layout.
7. **Reservation strategy** (§4.3) — product/economics decision on estimate vs
   charge-after.

---

## 12. Suggested build order (lowest risk first)

1. **Connection seam + singleton** (§8, §9) — nothing works without this, and it's
   pure plumbing with no product decisions.
2. **Rate limiting** (§7) — simplest correct use, good place to validate the seam
   and the atomic pattern on something low-stakes.
3. **Background job status** (§6.1 only) — status store, defer the executor
   decision.
4. **Session state** (§5) — needs your context schema; medium complexity.
5. **Token budget** (§4) — most correctness-critical; do it last, when the seam
   and the atomic Lua pattern are already proven by the rate limiter.

This order means the dangerous, money-touching code (budgets) is written only
after you've exercised the same primitives (atomic Lua, the connection seam) on
something that can't hurt a paying customer.
