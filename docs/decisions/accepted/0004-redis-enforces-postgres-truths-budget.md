# 0004 — Redis enforces token budgets atomically; Postgres is the truth

> **Status:** partially implemented, enforcement **OFF**. Redis-Lua atomic
> reserve/reconcile, seeding, and the per-call LLM anchor exist and are tested.
> Production seeding, anniversary-period wiring, durable Postgres synchronization,
> and Postgres RLS remain unbuilt; do not claim atomic budgets or RLS as shipped
> guarantees while `enforcement_enabled` is false. (Tracked: issue #14.)
> **Date recorded:** 2026-06-15 (back-filled; decision predates this record)
> **Supersedes / superseded by:** —
> **Authority:** Tier 7 (ADR). Reflected as Invariants §V.21–22.

## Context

Token budgets must be enforced in real time on every LLM call, with no
race-condition overspend, while remaining durable and auditable for billing.
A naive read-check-decrement in application code is a classic lost-update race;
a plain `DECRBY` cannot refuse to go negative.

## Decision

Two stores with distinct roles:

- **Redis** is the real-time enforcement layer. Check-and-decrement is **one
  atomic operation** on the server (Lua via `EVAL`), so concurrent calls cannot
  both pass a near-empty budget. Keyed `budget:{user_id}:{billing_period}`.
- **Postgres** is the durable source of truth (billing, reset history, audit),
  synced asynchronously from Redis; never on the per-call hot path.

Budget resets are triggered by Stripe `invoice.paid` webhooks, writing the fresh
budget to both stores. On a Redis budget-check failure, **fail closed** with a
clear "service degraded" message (protects margin; defensible for a paid product).

## Alternatives considered

- **Read-then-write in Python** — rejected: lost-update race drives budgets
  negative.
- **Plain `DECRBY`** — rejected: atomic but cannot refuse to go negative.
- **Postgres on the hot path** — rejected: too slow for per-call enforcement.

## Consequences & risks

- Correct, fast enforcement; durable truth survives a Redis flush.
- Open sub-decisions remain (estimate-then-reconcile vs charge-after; billing
  period definition) — tracked in the storage doc's `[NEEDS YOUR CODE]` list.

## Source

[../../architecture/SYSTEM_ARCHITECTURE.md](../../architecture/SYSTEM_ARCHITECTURE.md)
→ Token Budget System; [../../architecture/storage/REDIS_ARCHITECTURE.md](../../architecture/storage/REDIS_ARCHITECTURE.md)
→ §4; project `CLAUDE.md` → Hard Constraints #7.
