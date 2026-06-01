"""Agent-owned memory gateway.

Memory is part of the orchestrator's cognition, not an external tool. This file
keeps the agent-facing memory API small, bounded, and explicit while delegating
storage/indexing details to `src.memory`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from src.memory.coordinator import MemoryCoordinator, memory_coordinator
from src.memory.local_index import MemoryRecord


@dataclass(slots=True, frozen=True)
class AgentMemoryLimits:
    """Bounds applied before the agent reads from or writes to memory."""

    max_search_limit: int = 20
    max_content_chars: int = 12000
    default_trust: float = 0.55
    min_trust: float = 0.0
    max_trust: float = 1.0

    def bounded_limit(self, value: int) -> int:
        """Clamp caller-requested result counts to a safe search limit."""
        return max(1, min(int(value), self.max_search_limit))

    def bounded_content(self, value: str) -> str:
        """Trim stored content so accidental huge memories do not bloat recall."""
        return value[: self.max_content_chars]

    def bounded_trust(self, value: float | None) -> float:
        """Clamp trust scores into the valid memory range."""
        if value is None:
            value = self.default_trust
        return max(self.min_trust, min(float(value), self.max_trust))


class AgentMemory:
    """Agent-owned memory gateway.

    Memory is part of the orchestrator's context and judgment. It is not exposed
    as an external primitive tool.
    """

    def __init__(
        self,
        coordinator: MemoryCoordinator | None = None,
        limits: AgentMemoryLimits | None = None,
    ) -> None:
        """Use an injected coordinator for tests or the global coordinator by default."""
        self.coordinator = coordinator or memory_coordinator
        self.limits = limits or AgentMemoryLimits()

    async def essential_context(self, user_query: str = "") -> str:
        """Return prompt-ready memory context for governance/system prompting."""
        return await self.coordinator.get_essential_context_async(user_query.strip())

    async def search(
        self,
        query: str,
        *,
        limit: int = 8,
        kinds: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """Search memory asynchronously with empty-query and result-count guards."""
        query = query.strip()
        if not query:
            return {"results": [], "count": 0}

        return await self.coordinator.search_all_async(
            query,
            limit=self.limits.bounded_limit(limit),
            kinds=kinds,
        )

    def search_sync(
        self,
        query: str,
        *,
        limit: int = 8,
        kinds: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """Search memory synchronously for call sites outside an event loop."""
        query = query.strip()
        if not query:
            return {"results": [], "count": 0}

        hits = self.coordinator.memory.search_sync(
            query,
            limit=self.limits.bounded_limit(limit),
            kinds=kinds,
        )
        return {"results": hits, "count": len(hits)}

    async def remember(
        self,
        *,
        source_id: str,
        kind: str,
        title: str,
        content: str,
        trust: float | None = None,
        pinned: bool = False,
        valid_until: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Store a structured memory record through the async coordinator path."""
        record = self._record(
            source_id=source_id,
            kind=kind,
            title=title,
            content=content,
            trust=trust,
            pinned=pinned,
            valid_until=valid_until,
            metadata=metadata,
        )
        await self.coordinator.remember_many_async([record])
        return {"stored": True, "source_id": record.source_id, "kind": record.kind}

    def remember_sync(
        self,
        *,
        source_id: str,
        kind: str,
        title: str,
        content: str,
        trust: float | None = None,
        pinned: bool = False,
        valid_until: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Store a structured memory record through the sync memory engine path."""
        record = self._record(
            source_id=source_id,
            kind=kind,
            title=title,
            content=content,
            trust=trust,
            pinned=pinned,
            valid_until=valid_until,
            metadata=metadata,
        )
        self.coordinator.memory.remember_sync(record)
        return {"stored": True, "source_id": record.source_id, "kind": record.kind}

    def _record(
        self,
        *,
        source_id: str,
        kind: str,
        title: str,
        content: str,
        trust: float | None,
        pinned: bool,
        valid_until: str | None,
        metadata: dict[str, Any] | None,
    ) -> MemoryRecord:
        """Validate and normalize user-facing memory fields into MemoryRecord."""
        source_id = source_id.strip()
        kind = kind.strip()
        title = title.strip()
        content = self.limits.bounded_content(content.strip())

        if not source_id:
            raise ValueError("source_id is required")
        if not kind:
            raise ValueError("kind is required")
        if not title:
            raise ValueError("title is required")
        if not content:
            raise ValueError("content is required")

        return MemoryRecord(
            source_id=source_id,
            kind=kind,
            title=title,
            content=content,
            trust=self.limits.bounded_trust(trust),
            pinned=pinned,
            valid_until=valid_until,
            metadata=metadata or {},
        )


agent_memory = AgentMemory()
