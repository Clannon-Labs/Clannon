# 0002 — One Qdrant instance, scoped by `user_id` payload filter

> **Status:** accepted
> **Date recorded:** 2026-06-15 (back-filled; decision predates this record)
> **Supersedes / superseded by:** —
> **Authority:** Tier 7 (ADR). Reflected as Invariant §V.20.

## Context

Memory vectors for many users must be isolated for tenancy, but per-user vector
collections proliferate operationally and scale badly. The system needs strong
isolation without collection sprawl.

## Decision

Use a **single Qdrant instance** with shared collections. Isolate tenants by a
mandatory **`user_id` payload filter** applied at query time, enforced at the
Memory Manager boundary — no other module may construct a raw Qdrant query. A CI
check (Semgrep) blocks any user-data query lacking a scope filter, making
unscoped access a build failure rather than a convention.

## Alternatives considered

- **Per-user collections** — rejected: collection proliferation, operational
  cost, no real security gain over payload filtering done correctly.
- **Separate Qdrant instances per tenant** — rejected: untenable at solo-founder
  scale and unnecessary for the threat model.

## Consequences & risks

- Simple infrastructure; one instance to operate and back up.
- Isolation correctness depends entirely on the `user_id` filter always being
  present — hence the single boundary + CI enforcement.
- Risk: a code path that bypasses the Memory Manager. The "only the Manager
  queries Qdrant" rule and the Semgrep gate exist to prevent this.

## Source

[../../architecture/SYSTEM_ARCHITECTURE.md](../../architecture/SYSTEM_ARCHITECTURE.md)
→ Vector Store Architecture; `backend/core/memory/ARCHITECTURE.md` → identity
model; project `CLAUDE.md` → Hard Constraints #8.
