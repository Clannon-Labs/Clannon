"""
The cross-batch awareness boundary.

The contract the consumer (a batch orchestrator, which reads "what are the OTHER batches
in my mission doing?" to delegate/flag) and the implementer (`core/memory`, keyed on the
same `user_id` discipline as the rest of the memory subsystem) agree on, so neither imports
the other — the same one-door / sole-broker pattern as `MemoryPort`/`GraphPort`/`BudgetPort`.

Ratified 2026-07-05 (Q1 ruling: a SEPARATE port, NOT a `MemoryPort` method — batch-lifecycle
status is control-plane state, not epistemic memory; a distinct axis, store, and access
pattern, so its own door keeps every contract single-purpose). Implemented 2026-07-05/06 in
`core/memory` (`batch_awareness_manager.py` + `batch_store.py`, covered by
`tests/memory_batch_awareness.py`): `mission_id`/`batch_id` flow through trusted `ctx`, and
the Mission Engine's conclude-path drives `clear_mission`. The remaining open work is the
CONSUMER — a batch orchestrator reading `cross_batch_awareness()` and sizing the result into
its own context budget — which lands with the batch-orchestrator step, not here.

The read is a bounded, deterministic filter (never a relevance-ranked search — there is no
query), so a batch orchestrator learns just enough to coordinate without the context bloat a
full other-batch dump would cause.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from foundation.vocab.types import BatchLifecycleStatus


@dataclass(frozen=True, slots=True)
class BatchAwarenessItem:
    """One OTHER batch's current status — thin by CONSTRUCTION, not convention: this shape
    structurally cannot carry a finding, a transcript, or any other batch's detail. A
    schema-minimality test pins the field set so a future addition is a conscious review, not
    drift. `updated_at` is a unix ts (matching the memory subsystem's existing float-ts
    convention), NOT a datetime."""
    batch_id: str
    domain: str
    status: BatchLifecycleStatus
    headline: str            # hard-capped at write time (a single-line gist, never a body)
    updated_at: float = 0.0  # unix ts


@dataclass(slots=True)
class CrossBatchAwareness:
    """The bounded projection returned to a batch orchestrator. `total_batches` is the TRUE
    count for the mission even when `items` is truncated — `total_batches > len(items)` is the
    structural "truncation happened" signal, so a silently-dropped blocked batch can never
    read as "no such batch" (that would be a correctness bug, not a display quirk)."""
    items: list[BatchAwarenessItem] = field(default_factory=list)
    total_batches: int = 0
    degraded: bool = False       # store down/disabled — never raise; mirror the other ports
    notes: str = ""


@runtime_checkable
class BatchAwarenessPort(Protocol):
    """The ONLY way a batch orchestrator reads/writes cross-batch status; the `core/memory`
    implementer is the sole broker. `user_id` is MANDATORY and fail-closed on every method
    (a missing scope returns an empty degraded read / a no-op write, never a cross-tenant
    leak — the §V.20 discipline, unchanged). `mission_id`/`batch_id`/`requesting_batch_id`
    enter from trusted `ctx` only, never model output (identity-set-once)."""

    async def record_batch_status(
        self, user_id: str, mission_id: str, batch_id: str, domain: str,
        status: BatchLifecycleStatus, headline: str,
    ) -> bool:
        """Deterministic key-upsert of ONE current-status record for
        (user_id, mission_id, batch_id) — a HARD replace (the old status is gone), NOT the
        cosine-dedup soft-merge `record_write_proposals` uses (a status transition
        ACTIVE→BLOCKED must overwrite, not accumulate). Returns whether it was actually
        persisted — the same 'no phantom writes' honesty as the other doors. Called by the
        central orchestrator after a batch turn concludes, never by a batch about itself."""
        ...

    async def cross_batch_awareness(
        self, user_id: str, mission_id: str, requesting_batch_id: str,
    ) -> CrossBatchAwareness:
        """A deterministic, code-only, bounded projection of every OTHER batch's current
        status in this mission (excludes `requesting_batch_id` — a batch doesn't need itself).
        Never ranks by relevance (there is no query) — a complete filter-read, aggregate-size
        bounded, with status-priority truncation so a quiet BLOCKED/FAILED batch survives over
        a wave of ACTIVE ones. Fail-closed: missing `user_id`/`mission_id` → empty degraded
        result, never a cross-tenant leak."""
        ...
