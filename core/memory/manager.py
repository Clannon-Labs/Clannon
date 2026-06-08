"""
Memory Manager — the single door to the memory layer.

Everything that wants memory goes through this manager (it implements
`foundation.MemoryPort`); nothing outside imports memory internals. Memory is a
layer of its own and Vraksha's future moat, so this checkpoint keeps it
deliberately tiny and the real build (Qdrant + fastembed, the four tiers,
ranking/budget, a background memory-agent) is a dedicated next session.

Phase-1 behaviour: an in-process episodic store keyed by session_id. hydrate()
returns the most recent K entries; record_write_proposals() appends. State lives
only for the process lifetime (lost on restart) — enough for within-session
recall and to prove the port end to end.
"""

from __future__ import annotations

from foundation import (
    HydrationPackage,
    HydrationRequest,
    MemoryItem,
    MemoryWriteProposal,
)

_RECALL_K = 5


class MemoryManager:
    """Phase-1 in-memory episodic implementation of `foundation.MemoryPort`."""

    def __init__(self, recall_k: int = _RECALL_K) -> None:
        self._episodic: dict[str, list[MemoryItem]] = {}   # session_id -> items
        self._recall_k = recall_k

    async def hydrate(self, request: HydrationRequest) -> HydrationPackage:
        recent = self._episodic.get(request.session_id, [])[-self._recall_k:]
        return HydrationPackage(
            items=list(recent),
            notes=None if recent else "no prior episodic memory",
        )

    async def record_write_proposals(
        self, session_id: str, proposals: list[MemoryWriteProposal]
    ) -> None:
        if not proposals:
            return
        bucket = self._episodic.setdefault(session_id, [])
        for proposal in proposals:
            bucket.append(
                MemoryItem(store=proposal.store, content=proposal.content, score=proposal.confidence)
            )


# Process-level singleton so within-session recall survives across turns in one run.
manager = MemoryManager()
