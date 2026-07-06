"""
Memory Manager — the single door to the memory layer (foundation.MemoryPort).

Real implementation per ARCHITECTURE.md: four Qdrant tiers scoped by user_id,
nomic embeddings, trust-aware ranking with recency decay, Lagrangian
(water-filling) token budgeting at hydration, and a write policy that owns
what proposals become. Every failure degrades — memory never fails a run.

This class is THE `MemoryPort` door only — the ranking/budgeting internals
live in `hydration.py` and the dedup/supersession internals live in
`write_policy.py` (split out 2026-07-06, LAW 2: this file was pushing the
500-line ceiling with no headroom). Same adapter/internals relationship
`graph_manager.py` has to `graph_store.py`.
"""

from __future__ import annotations

import asyncio
import logging

from foundation import HydrationPackage, HydrationRequest, MemoryWriteProposal

from . import batch_awareness_manager, graph_manager, hydration, store, write_policy, writer

log = logging.getLogger(__name__)


class MemoryManager:
    """Qdrant-backed implementer of foundation.MemoryPort."""

    async def hydrate(self, request: HydrationRequest) -> HydrationPackage:
        return await hydration.hydrate(request)

    async def record_write_proposals(
        self, user_id: str, session_id: str, proposals: list[MemoryWriteProposal]
    ) -> list[MemoryWriteProposal]:
        return await write_policy.record_write_proposals(user_id, session_id, proposals)

    async def learn(
        self, user_id: str, session_id: str, *, task: str, answer: str, findings: list[str]
    ) -> None:
        """The background memory-agent: distil semantic facts + procedural patterns
        from a finished turn and persist what clears the write policy. Best-effort —
        a fault here never affects the turn that already answered the user."""
        if not user_id:
            return
        try:
            proposals = await writer.distill(task, answer, findings)
        except Exception as exc:  # noqa: BLE001 — never let learning break a turn
            log.warning("memory distillation failed: %s", exc)
            return
        if proposals:
            await self.record_write_proposals(user_id, session_id, proposals)

    # ---- delivery-layer surface (not part of MemoryPort) ----------------

    async def sync_wiki(self, user_id: str, title: str, content: str) -> None:
        await write_policy.sync_wiki(user_id, title, content)

    async def delete_user(self, user_id: str) -> None:
        """Right-to-erasure: purge every tier for this user — the four
        Qdrant vector tiers, the graph tier (CodeFile + Mission/Task), and
        the cross-batch awareness tier."""
        await asyncio.to_thread(store.delete_user, user_id)
        await graph_manager.manager.delete_user(user_id)
        await batch_awareness_manager.manager.delete_user(user_id)


# Process-level singleton; wiring hands this to the orchestrator's ports.
manager = MemoryManager()
