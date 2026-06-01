from __future__ import annotations

from typing import Any, Dict, Sequence

from src.memory.background import run_background_consolidation
from src.memory.local_index import LocalFirstMemory, MemoryRecord, get_memory


class MemoryCoordinator:
    """A unified gateway to orchestrate retrieval across Vraksha's Tri-Store backends.

    In a complex agentic system, the Agent (the 'Brain') should not be coupled 
    to the specific mechanics of its long-term storage. This class acts as a 
    single interface that hides the complexity of whether a fact came from 
    a Markdown file (Wiki), a conceptual store (Semantic), or the primary 
    search index (SQLite).

    By centralizing retrieval here, we can inject new storage technologies — 
    such as a Graph Database or a dedicated Vector DB — without modifying the 
    core agent engine. It ensures that the agent always interacts with a 
    consistent, high-level memory API.
    """

    def __init__(self, memory: LocalFirstMemory | None = None):
        # We default to the global singleton engine to keep things centralized.
        self.memory = memory or get_memory()

    async def get_essential_context_async(self, user_query: str = "") -> str:
        """Retrieves the bedrock identity and recent session context for the prompt."""
        return await self.memory.essential_context(user_query)

    async def search_all_async(self, query: str, *, limit: int = 8, kinds: Sequence[str] | None = None) -> Dict[str, Any]:
        """Keyword search across all indexed documents and files."""
        hits = await self.memory.search(query, limit=limit, kinds=kinds)
        return {"results": hits, "count": len(hits)}

    async def remember_many_async(self, records: list[MemoryRecord]) -> None:
        """Commits multiple facts/events to long-term storage."""
        await self.memory.remember_many(records)

    def run_background_consolidation(self, messages: list[dict[str, Any]]) -> None:
        run_background_consolidation(messages)


memory_coordinator = MemoryCoordinator()
