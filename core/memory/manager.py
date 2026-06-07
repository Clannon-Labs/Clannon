"""
Memory Manager — the single door to the memory layer.

Everything that wants memory goes through this manager (it implements
`foundation.MemoryPort`). Nothing outside imports memory internals; the
orchestrator holds only the port. This keeps memory a self-contained layer that
can grow its own machinery (stores, trust/policy, the four tiers, Qdrant) behind
this interface without touching callers.

Phase 1 is a stub: hydration returns empty and write proposals are accepted but
not persisted. The shape is real so the orchestrator integrates against the final
contract today.

TODO (real memory layer, built entirely inside core/memory/):
- proactive hydration across wiki/semantic/episodic/procedural tiers,
- Lagrangian token-budget allocation across tiers,
- Qdrant-backed retrieval (single instance, user_id payload filter),
- trust/recency ranking; wiki overrides inferred memory,
- a BACKGROUND memory-agent with its own LLM call (consolidation/compaction),
- write policy that decides whether/where each proposal is persisted.
"""

from __future__ import annotations

from foundation import HydrationPackage, HydrationRequest, MemoryWriteProposal


class MemoryManager:
    """Phase-1 stub implementation of `foundation.MemoryPort`."""

    def __init__(self) -> None:
        # Stub visibility only: proposals seen this run, so tests/callers can
        # confirm they reached the door. The real manager persists via policy.
        self.recorded_proposals: list[MemoryWriteProposal] = []

    async def hydrate(self, request: HydrationRequest) -> HydrationPackage:
        """Return an empty package for now (no retrieval wired yet)."""
        return HydrationPackage(notes="memory stub: no hydration")

    async def record_write_proposals(self, proposals: list[MemoryWriteProposal]) -> None:
        """Accept proposals without persisting them (stub)."""
        self.recorded_proposals.extend(proposals)
