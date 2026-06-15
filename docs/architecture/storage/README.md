# Storage

> **Purpose:** Entry point for where Clannon's state lives and which store is the
> truth for what.
> **Scope:** Redis (budgets, hot session state, job tracking, rate limiting),
> Postgres (durable truth), Qdrant (vectors), Cloudflare R2 (wiki files), and the
> local-vs-cloud mapping. Memory *semantics* are in [../memory/](../memory/);
> this folder is the infrastructure beneath them.
> **Authority level:** Tier 5 (Subsystem). Inherits
> [../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md) and the Invariants.
> **Related:** [../memory/](../memory/) · [../security/](../security/) ·
> [../../glossary/TERMS.md](../../glossary/TERMS.md)

## Contents

- **[REDIS_ARCHITECTURE.md](REDIS_ARCHITECTURE.md)** — the four Redis jobs
  (token budget, hot session state, background-job tracking, rate limiting),
  the atomic-decrement decision, the Redis↔Postgres split, the connection model,
  and the open `[NEEDS YOUR CODE]` decisions. Tagged as a **post-Macondo /
  production** design reference.

## Canonical design

[../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md):

- **Token Budget System** — Redis atomic decrement + Postgres durable truth.
- **Session Continuity** — Redis hot session state as a disposable cache.
- **Background Jobs And Async Work** — job state under a job ID in Redis.
- **Vector Store Architecture** — single Qdrant instance, `user_id` payload scope.
- **Infrastructure Summary** — the full local-dev vs cloud/production table.

## Store-by-store truth ownership

| Store | Role | Source of truth? |
|---|---|---|
| Postgres (Supabase, RLS) | durable state, billing, audit | **Yes** |
| Redis (Upstash in prod) | fast enforcement + hot cache | No — rebuildable / reconciled |
| Qdrant | memory vectors | per-tier truth, scoped by `user_id` |
| Cloudflare R2 | wiki `.md` files | yes, for wiki content |

## Key invariants this subsystem must honor

- Token-budget check-and-decrement is one atomic operation; never read-then-write.
- Postgres is durable truth; Redis can be flushed without losing legal/financial
  state.
- Every user-scoped key/row carries the authenticated `user_id`; RLS uses
  transaction-local `SET LOCAL`, never connection-level `SET`.
- One Qdrant instance, scoped by `user_id` payload — never per-user collections.
