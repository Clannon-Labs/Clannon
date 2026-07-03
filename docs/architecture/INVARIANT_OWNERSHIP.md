# INVARIANT OWNERSHIP

> **Purpose:** Map every invariant to its **implementation owner** and tell the
> truth about whether it is **enforced in code**, **partially enforced**, or
> still **aspirational**. This is correctness tooling: it exists so a new agent
> can distinguish a binding, code-backed guarantee from a documented intention.
> **Scope:** All 27 invariants in [../vision/INVARIANTS.md](../vision/INVARIANTS.md).
> **Authority level:** Cross-cutting reference. It does **not** create or weaken
> invariants — it reports their enforcement state. The invariant text in
> `INVARIANTS.md` remains authoritative; if this matrix and an invariant
> disagree, fix the matrix.
> **Related:** [../vision/INVARIANTS.md](../vision/INVARIANTS.md) ·
> [ARCHITECTURAL_CONVENTIONS.md](ARCHITECTURAL_CONVENTIONS.md) ·
> [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md)

## Status legend

- **enforced** — a code path (or, for process rules, a process artifact) makes
  the invariant hold today.
- **partial** — partly enforced; a named gap remains.
- **aspirational** — documented as a rule but **no enforcing code exists yet**.
  A reader must NOT assume the system guarantees this.

> **Why this document earns its keep:** building this matrix surfaced gaps between
> documented and enforced guarantees. Fully **aspirational** (no enforcing code):
> atomic token budgets (§21), tenant-isolation/RLS (§22), typed knowledge (§3),
> and the institutional/decision-memory promotion rules (§2, §8). One is
> **partial**: §20's runtime `user_id` scoping **is** enforced and tested
> (`tests/memory_isolation.py`), and a runnable grep-based stand-in now exists at
> `backend/scripts/check_invariants.py` (exits 0 on clean tree), but the full
> Semgrep CI build-gate (issue #15) is still absent. None should be relied on beyond its stated status.
> (Verified: `grep DECRBY|EVAL|SET LOCAL|invoice.paid|promotion|EntryType` and a
> search for a Semgrep config returned nothing in `backend/`; tenant isolation is
> exercised by `tests/memory_isolation.py`, and provider fallback by
> `tests/llm_retry.py`.)

## Ownership matrix

| § | Invariant (short) | Owner (module / artifact) | Enforcement mechanism | Verification | Status |
|---|---|---|---|---|---|
| I.1 | Memory is first-class | `core/memory/` | 4-tier store behind MemoryPort | subsystem exists & runs | enforced |
| I.2 | Institutional > conversation (promotion priority) | — (proposed) | promotion ordering not in code | grep: none | **aspirational** |
| I.3 | Typed knowledge, no unstructured blob | — (proposed) | no `EntryType`/schema enum | grep: none | **aspirational** |
| I.4 | Wiki beats everything | `core/memory/manager.py` | `_TIER_TRUST` ranking (wiki highest) | manager.py:29 | enforced |
| I.5 | Episodic is the baseline tier | `core/memory` (tier) / billing | episodic tier built; **plan-gating not built** (no billing) | tiers in store/writer | partial |
| I.6 | Experts never write memory directly | `core/memory/writer.py` + `foundation/contracts/memory.py` | experts hold only MemoryPort; writes go through writer | port-only surface | enforced |
| I.7 | Memory reached only through MemoryPort | `foundation/contracts/memory.py` + `core/memory` | callers hold the Protocol, not internals | import surface | enforced |
| II.8 | Artifacts over hidden context (institutional) | — (proposed) | institutional artifact protocol not built (note: `ArtifactStore` is **output files**, a different system) | grep/contracts | **aspirational** |
| II.9 | No critical decision only in code | `docs/decisions/` | ADR system exists | this repo | enforced (process) |
| II.10 | Session continuity is silent | `core/memory` (hydration) / session store | hydration exists; **rollover/compaction store not built** (Redis absent) | manager.py; grep | partial |
| III.11 | Flow is the only inter-stage transport | `foundation/transport/flow.py` | `Flow.load/next/block/warn/fail` | flow.py; FLOW_GUIDE | enforced |
| III.12 | LLM framework confined to `core/llm` | `core/llm/framework.py` | single entry; no other prod import of `pydantic_ai` | grep (only tests import elsewhere) | enforced |
| III.13 | One entry point per layer | each layer `__init__` + `ARCHITECTURAL_CONVENTIONS.md` | single door per layer | per-layer review | enforced (convention) |
| IV.14 | Security before execution | `core/intake` → `security/sanitizers` → `core/normalizer` → `core/verifier` | ordered pre-orchestrator pipeline | stages exist & ordered | enforced |
| IV.15 | Verifier sole input blocker / filter sole output gate | `core/verifier` + `security/filter` | structured gates | modules exist | enforced |
| IV.16 | Normalization is code-only | `core/normalizer` | no LLM call in stage | code review | enforced |
| IV.17 | All fetched/retrieved content is untrusted | `tools/` + `security/sanitizers` | fetched content should re-enter sanitization | **verify routing** | partial |
| IV.18 | Identity set once, never re-derived | `foundation/transport/context.py` + `api/` auth | `user_id` in Flow context | context.py | enforced |
| IV.19 | User input is never a filesystem path | `foundation/coercion.py` | `coerce_to_bytes` boundary | coercion.py | enforced |
| V.20 | One Qdrant instance, `user_id`-scoped **+ CI gate** | `core/memory` (runtime); CI (partial) | runtime payload filter enforced **and tested**; Semgrep CI gate still absent (issue #15); **grep-based stand-in present** | `tests/memory_isolation.py` (tenant isolation); `backend/scripts/check_invariants.py` (runnable stand-in, exits 0 on clean tree) | partial |
| V.21 | Token-budget decrements are atomic | — (design only) | Lua `EVAL` pattern designed, not built | `REDIS_ARCHITECTURE.md`; grep: none | **aspirational** |
| V.22 | No tenant leakage via keys/rows (RLS) | — (design only) | RLS/`SET LOCAL` designed, not built | grep: none | **aspirational** |
| VI.23 | Capability first, provider second | `core/llm` (registry) + `models.yaml` | capability-filtered model routing | registry + config | enforced |
| VI.24 | Never trust one provider/model/embedding | `backend/models.yaml` + `core/llm/retry.py` (fallback chains) | cross-provider fallback routing | **tested** — `tests/llm_retry.py` (fallback-chain exhaustion) | enforced |
| VI.25 | Media becomes knowledge | `experts/media` (preprocess) / knowledge graph | preprocessing built; **graph/“becomes knowledge” not built** | preprocess.py; grep | partial |
| VI.26 | Raw assets forever; representations disposable | — (proposed) | no raw-asset lineage/store system | grep | **aspirational** |
| VII.27 | Capability visibility over elegance | `vision/ATTENTION_THRESHOLD.md` | strategic/process rule | vision doc | enforced (process) |

## How to use this matrix

- **Before claiming a guarantee** (in a demo, a doc, or to a user), check the
  status. Do not present an **aspirational** invariant as a feature.
- **When you build an aspirational invariant**, change its row to partial/enforced
  in the same pass and name the new owner module.
- This matrix is the discoverable answer to "who enforces invariant X, and is it
  actually enforced?" — keep statuses coarse so it changes rarely.
