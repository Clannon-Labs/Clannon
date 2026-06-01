from __future__ import annotations

from typing import Any, Dict, List

from src.memory.base import BaseMemoryLayer
from src.memory.local_index import MemoryRecord, get_memory


class GraphLayer(BaseMemoryLayer):
    """Local relational-memory facade.

    Natural-language graph facts are stored as typed local records. This avoids
    executing user text as Cypher and keeps retrieval local-first.
    """

    def __init__(self):
        self.memory = get_memory()

    def add(self, content: Any, **kwargs) -> bool:
        text = str(content)
        record = MemoryRecord(
            source_id=kwargs.get("session_id") or kwargs.get("source_id") or "graph",
            kind=kwargs.get("category", "fact"),
            title=kwargs.get("title", "relational fact"),
            content=text,
            trust=float(kwargs.get("trust", kwargs.get("trust_score", 0.70))),
            pinned=bool(kwargs.get("pinned", False)),
            valid_until=kwargs.get("valid_until"),
            metadata={k: v for k, v in kwargs.items() if k not in {"session_id", "source_id", "category", "title", "trust", "trust_score", "pinned", "valid_until"}},
        )
        self.memory.remember_sync(record)
        return True

    def search(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        return self.memory.search_sync(query, limit=int(kwargs.get("limit", 5)), kinds=kwargs.get("kinds"))

    def get_essential_context(self) -> str:
        return ""


async def add_episode(content: str, session_id: str) -> None:
    await get_memory().remember(MemoryRecord(
        source_id=session_id,
        kind="episode",
        title="conversation episode",
        content=content,
        trust=0.55,
    ))


async def search(query: str) -> list[dict[str, Any]]:
    return await get_memory().search(query, limit=5)


graph_layer = GraphLayer()
