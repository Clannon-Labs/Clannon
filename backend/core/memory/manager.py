"""
Memory Manager — the single door to the memory layer (foundation.MemoryPort).

Real implementation per ARCHITECTURE.md: four Qdrant tiers scoped by user_id,
nomic embeddings, trust-aware ranking with recency decay, Lagrangian
(water-filling) token budgeting at hydration, and a write policy that owns
what curated tool actions become. Every failure degrades — memory never fails a run.

This class is THE `MemoryPort` door only — the ranking/budgeting internals
live in `hydration.py` and the dedup/supersession internals live in
`write_policy.py` (split out 2026-07-06, LAW 2: this file was pushing the
500-line ceiling with no headroom). Same adapter/internals relationship
`graph_manager.py` has to `graph_store.py`.
"""

from __future__ import annotations

import asyncio
import logging
import math

import settings
from foundation import (
    HydrationPackage,
    HydrationRequest,
    MemoryItem,
    MemoryStore,
    MemoryTurn,
    MemoryWriteProposal,
)

from . import (
    batch_awareness_manager,
    curator,
    deep_reader,
    graph_manager,
    hydration,
    items,
    store,
    write_policy,
)

log = logging.getLogger(__name__)


class MemoryManager:
    """Qdrant-backed implementer of foundation.MemoryPort."""

    async def hydrate(self, request: HydrationRequest) -> HydrationPackage:
        """Return deterministic scoped hydration; never add a model call here."""
        return await hydration.hydrate(request)

    async def deepen(
        self,
        request: HydrationRequest,
        fast: HydrationPackage,
    ) -> HydrationPackage:
        """Post-verifier internal read: enrich hard queries through bounded tools."""
        if fast.degraded or not deep_reader.needs_deep_retrieval(request):
            return fast
        deep = await deep_reader.retrieve(request)
        return deep_reader.merge(request, fast, deep)

    async def process_turn(self, turn: MemoryTurn) -> list[MemoryItem]:
        return await curator.process_turn(turn)

    async def list_entries(self, user_id: str) -> list[MemoryItem]:
        """List bounded inferred memory under one trusted tenant scope."""
        if not user_id:
            return []
        tiers = (
            MemoryStore.SEMANTIC,
            MemoryStore.EPISODIC,
            MemoryStore.PROCEDURAL,
        )
        per_tier_limit = math.ceil(settings.MEMORY.list_max_entries / len(tiers))
        results = await asyncio.gather(
            *(
                asyncio.to_thread(store.list_entries, tier, user_id, per_tier_limit)
                for tier in tiers
            ),
            return_exceptions=True,
        )
        listed: list[MemoryItem] = []
        for tier, result in zip(tiers, results):
            if isinstance(result, BaseException):
                log.warning("memory list failed for %s: %s", tier.value, result)
                continue
            listed.extend(items.from_payload(tier, payload) for payload in result)
        listed.sort(key=lambda item: item.created_at, reverse=True)
        return listed[: settings.MEMORY.list_max_entries]

    async def delete_entry(self, user_id: str, memory_id: str) -> bool:
        """Delete one inferred point without disclosing foreign/missing ids."""
        if not user_id or not memory_id:
            return False
        return await asyncio.to_thread(store.delete_entry, user_id, memory_id)

    # ---- legacy/internal compatibility; intentionally absent from MemoryPort ----

    async def record_write_proposals(
        self, user_id: str, session_id: str, proposals: list[MemoryWriteProposal]
    ) -> list[MemoryWriteProposal]:
        """Benchmark/tooling compatibility. Runtime callers use ``process_turn``."""
        return await write_policy.record_write_proposals(user_id, session_id, proposals)

    async def learn(
        self, user_id: str, session_id: str, *, task: str, answer: str, findings: list[str]
    ) -> None:
        """Temporary caller shim. The curator still owns every memory decision."""
        try:
            await self.process_turn(
                MemoryTurn(
                    user_id=user_id,
                    session_id=session_id,
                    trace_id="",
                    request=task,
                    response=answer,
                    findings=tuple(findings),
                )
            )
        except Exception as exc:  # noqa: BLE001 - compatibility path stays best-effort
            log.warning("legacy memory learn shim degraded: %s", exc)

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


# Process-level singleton used only by memory-owned pipeline stages and authenticated API delivery.
manager = MemoryManager()
