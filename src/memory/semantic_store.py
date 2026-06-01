from __future__ import annotations

# from typing import Any

from src.memory.base import BaseMemoryLayer
from src.memory.local_index import MemoryRecord, get_memory

class SemanticLayer(BaseMemoryLayer):
    """A conceptual shim for storing fuzzy facts and session preferences.
    
    While the Wiki is for hard rules, the SemanticLayer is for the 'vague' 
    information that the agent picks up over time — such as user coding styles, 
    preferred naming conventions, or project context.
    
    Architecturally, this layer serves as a 'Shim'. It currently maps to 
    the local SQLite search engine, but it is defined as a separate layer to 
    allow for a seamless transition to a dedicated Vector Database (like 
    Qdrant or Pinecone) once the agent's conceptual memory requirements 
    exceed the limits of local search.
    """

    def __init__(self):
        self.memory = get_memory()

    def add(self, content: str, **kwargs) -> bool:
        """Registers a conceptual fact into the global memory index."""
        record = MemoryRecord(
            source_id=kwargs.get("session_id") or kwargs.get("source_id") or "semantic",
            kind=kwargs.get("category", "preference"),
            title=kwargs.get("title", kwargs.get("category", "semantic memory")),
            content=content,
            trust=float(kwargs.get("trust", 0.65)),
            pinned=False,
            metadata={k: v for k, v in kwargs.items() if k not in {"category", "title", "trust"}},
        )
        self.memory.remember_sync(record)
        return True

semantic_layer = SemanticLayer()
