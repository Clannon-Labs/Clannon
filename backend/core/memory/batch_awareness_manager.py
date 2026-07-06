"""
Batch Awareness Manager — the single door to the cross-batch awareness layer
(foundation.BatchAwarenessPort).

A separate class from `MemoryManager` (Q1 ruling, 2026-07-05): batch-lifecycle
status is control-plane state, not epistemic memory, so it rides its own port
and its own implementer — also keeps this off `manager.py`, which was already
near the LAW-2 line ceiling. Delegates all Qdrant mechanics to `batch_store.py`
(this class does status-priority sorting/truncation + the completion-sweep
policy; `batch_store.py` does raw reads/writes), the same relationship
`graph_manager.py` has to `graph_store.py`.

Also owns the `clear_mission` sweep (2026-07-06 conclude-path ruling: POLL,
not push — no new MemoryPort/BatchAwarenessPort method for a mission's
conclusion; this manager reads the terminal MISSION graph node itself via
`GraphManager`, already same-tree). Two mechanisms:
  - poll-on-read: `cross_batch_awareness()` checks whether the SPECIFIC
    mission it was just asked about has concluded, and sweeps it if so —
    cheap (one extra graph read scoped to the one mission already being
    served), and correct for the common case (a batch orchestrator that
    queries a mission again after it concludes triggers its own cleanup).
  - periodic backstop (`sweep_terminal_missions`): scans ALL of a user's
    MISSION nodes and clears any terminal-but-unswept one — catches the
    solo-mission-never-queried-again case poll-on-read can't. Not wired to
    a scheduler here (no scheduling infra owned by this module); exposed as
    a plain callable for whatever process ends up invoking it periodically.
"""
from __future__ import annotations

import asyncio
import logging

from foundation import (
    BatchAwarenessItem,
    BatchLifecycleStatus,
    CrossBatchAwareness,
    GraphScope,
    NodeLabel,
)

from . import batch_store
from .graph_manager import manager as graph_manager

log = logging.getLogger(__name__)

_STATUS_PRIORITY = {
    BatchLifecycleStatus.BLOCKED: 0,
    BatchLifecycleStatus.FAILED: 0,
    BatchLifecycleStatus.ACTIVE: 1,
    BatchLifecycleStatus.DONE: 2,
}

# Mirrors core/orchestrator/mission.py's MissionStatus terminal set
# (DONE/FAILED/USER_ENDED) as raw strings. This module cannot import that
# enum directly (it's orchestrator-internal, not exported through
# foundation) — a MISSION graph node's `status` property is an untyped
# string by the time it reaches here (GraphPort.write()'s `properties`
# dict has no type constraint). Flagged as a soft coupling in the
# batch-split proposal response, not a silent guess: if orchestration's
# terminal set ever changes, this constant must follow.
_TERMINAL_MISSION_STATUSES = frozenset({"done", "failed", "user_ended"})


def _to_item(row: dict) -> BatchAwarenessItem | None:
    """A row with an unrecognized status string is dropped, not crashed on —
    same "never raise into a read path" discipline as graph_manager's
    EdgeOrigin guard, for the identical reason (only reachable via a
    corrupt/hand-edited store; every write path only ever stores a real
    BatchLifecycleStatus.value)."""
    try:
        status = BatchLifecycleStatus(row.get("status", ""))
    except ValueError:
        log.warning("dropping batch-status row with an unrecognized status: %r", row.get("status"))
        return None
    return BatchAwarenessItem(
        batch_id=row.get("batch_id", ""),
        domain=row.get("domain", ""),
        status=status,
        headline=row.get("headline", ""),
        updated_at=float(row.get("updated_at", 0.0)),
    )


class BatchAwarenessManager:
    """Qdrant-backed implementer of foundation.BatchAwarenessPort."""

    async def record_batch_status(
        self, user_id: str, mission_id: str, batch_id: str, domain: str,
        status: BatchLifecycleStatus, headline: str,
    ) -> bool:
        if not user_id or not mission_id or not batch_id:
            return False
        return await asyncio.to_thread(
            batch_store.record_batch_status, user_id, mission_id, batch_id, domain, status, headline
        )

    async def cross_batch_awareness(
        self, user_id: str, mission_id: str, requesting_batch_id: str,
    ) -> CrossBatchAwareness:
        if not user_id or not mission_id:
            return CrossBatchAwareness(degraded=True, notes="missing user_id or mission_id — refused, fail-closed")

        await self._sweep_if_terminal(user_id, mission_id)

        read = await asyncio.to_thread(batch_store.scroll_batch_statuses, user_id, mission_id)
        if read.degraded:
            return CrossBatchAwareness(degraded=True, notes=read.notes)

        others = [r for r in read.rows if r.get("batch_id") != requesting_batch_id]
        items = [item for item in (_to_item(r) for r in others) if item is not None]
        items.sort(key=lambda item: (_STATUS_PRIORITY.get(item.status, 1), -item.updated_at))
        total = len(items)
        truncated = items[:batch_store.MAX_BATCHES_PER_MISSION]

        notes = ""
        if total > len(truncated):
            omitted = total - len(truncated)
            notes = f"showing {len(truncated)} of {total} batches; {omitted} lower-priority items omitted"
        return CrossBatchAwareness(items=truncated, total_batches=total, notes=notes)

    # ---- the clear_mission sweep (not part of BatchAwarenessPort) --------

    async def _sweep_if_terminal(self, user_id: str, mission_id: str) -> bool:
        """Poll-on-read: check whether THIS mission's MISSION node has
        concluded, and clear its batch-status points if so. Returns whether
        a sweep happened (used by tests; the read path ignores it). Never
        raises — a graph read fault here just means "not swept this time,"
        never a failure of the cross_batch_awareness read it's guarding.

        Second soft coupling (beyond `_TERMINAL_MISSION_STATUSES` above):
        this reads the MISSION node at `GraphScope(user_id=user_id)` —
        `repo_id=""`. Nothing in the codebase constructs a production
        `GraphScope` for a mission yet (`core/orchestrator/mission_operate.py`
        takes `scope` as a parameter from its own caller, not wired to real
        `ctx` yet); every existing mission_operate/mission_graph test uses
        `repo_id=""` too, so this matches the apparent convention, but it's
        unverified against real wiring. If a mission's real scope ever
        carries a non-empty `repo_id`, this silently never fires and the
        sweep never happens for that mission — flagged alongside the
        terminal-status coupling, not guessed past silently."""
        scope = GraphScope(user_id=user_id)
        result = await graph_manager.members(scope, NodeLabel.MISSION, parent_id=mission_id)
        if result.degraded or not result.nodes:
            return False
        status = result.nodes[0].properties.get("status", "")
        if status not in _TERMINAL_MISSION_STATUSES:
            return False
        await asyncio.to_thread(batch_store.clear_mission, user_id, mission_id)
        return True

    async def sweep_terminal_missions(self, user_id: str) -> int:
        """Periodic-maintenance backstop: scan every MISSION node this user
        has and clear batch-status points for any that have concluded.
        Catches the solo-mission-with-no-subsequent-read case poll-on-read
        can't reach. Returns the number of missions swept. Not scheduled by
        this module — a plain callable for whatever process ends up
        invoking it periodically. Same `repo_id=""` soft coupling as
        `_sweep_if_terminal` — see its docstring."""
        if not user_id:
            return 0
        scope = GraphScope(user_id=user_id)
        result = await graph_manager.members(scope, NodeLabel.MISSION)
        if result.degraded:
            return 0
        swept = 0
        for node in result.nodes:
            status = node.properties.get("status", "")
            if status not in _TERMINAL_MISSION_STATUSES:
                continue
            mission_id = node.properties.get("mission_id", "")
            if not mission_id:
                continue
            await asyncio.to_thread(batch_store.clear_mission, user_id, mission_id)
            swept += 1
        return swept

    async def delete_user(self, user_id: str) -> None:
        """Right-to-erasure: purge every batch-status point for this user.
        Not part of BatchAwarenessPort — a delivery-layer surface, same
        shape as MemoryManager.delete_user / GraphManager.delete_user, which
        calls this so an account deletion actually clears this tier too."""
        if not user_id:
            return
        await asyncio.to_thread(batch_store.delete_user, user_id)


# Process-level singleton; wiring hands this to the orchestrator's ports.
manager = BatchAwarenessManager()
