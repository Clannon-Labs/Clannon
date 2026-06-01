"""
Wiki Memory Layer for Vraksha.

The Wiki layer acts as the 'Immutable Truth' for the agent. It stores high-level
policies, project-wide rules, and core identity traits that should persist 
across all sessions and be prioritized during retrieval.

Unlike the Semantic or Graph stores, the Wiki is backed by curated Markdown 
files in the `memory/wiki/` directory.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from get_root import root
from src.memory.base import BaseMemoryLayer
from src.memory.local_index import MemoryRecord, bounded_read_text, get_memory
from src.memory.utils.async_journal_writer import atomic_append

ROOT = root.project
MEMORY_ROOT = ROOT / "memory"
WIKI_PATH = MEMORY_ROOT / "wiki"

class WikiLayer(BaseMemoryLayer):
    """Durable, human-auditable storage for deterministic project 'Truths'.
    
    Automated memory extraction is inherently probabilistic. Even the best 
    LLMs can occasionally misinterpret a conversation or 'hallucinate' a 
    new rule. The WikiLayer provides a hard override—a place where critical 
    project mandates are saved as plain Markdown files.
    
    This ensures that the most important facts (like identity, core rules, 
    and project requirements) are both human-editable and 100% durable. Every 
    entry in the Wiki is mirrored into the SQLite FTS5 index to provide 
    lightning-fast recall alongside its filesystem durability.
    """

    def __init__(self):
        WIKI_PATH.mkdir(parents=True, exist_ok=True)
        self.memory = get_memory()

    def add(self, content: str, filename: str = "rules.md", **kwargs) -> bool:
        """
        Appends content to a physical Markdown file AND updates the SQLite search index.
        """
        clean_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", filename)
        if not clean_name.endswith(".md"):
            clean_name += ".md"
            
        path = WIKI_PATH / clean_name
        
        # Physical File Commitment (Durable)
        atomic_append(path, f"\n\n{content.strip()}\n")
        
        # Search Index Commitment (Fast Recall)
        self.memory.remember_many_sync([MemoryRecord(
            source_id=f"wiki/{path.name}",
            kind="wiki",
            title=path.name,
            content=content,
            trust=float(kwargs.get("trust", 0.90)),
            pinned=True, # Wiki entries are treated as high-priority context
            metadata={"filename": path.name, "curated": True},
        )])
        return True

    def search(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """Keyword search across all wiki entries."""
        return self.memory.search_sync(
            query, 
            limit=int(kwargs.get("limit", 5)), 
            kinds=["wiki", "core"]
        )

    def get_essential_context(self) -> str:
        """
        Retrieves the 'Soul' and 'Rules' that form the bedrock of the 
        agent's personality and constraints.
        """
        parts: list[str] = []
        # Priority-ordered core files
        for label, path in [
            ("soul.md", MEMORY_ROOT / "soul.md"),
            ("rules.md", MEMORY_ROOT / "rules.md"),
            ("wiki/rules.md", WIKI_PATH / "rules.md"),
        ]:
            if path.exists():
                parts.append(f"### {label}\n{bounded_read_text(path)}")
        
        return "\n\n".join(parts)

wiki_layer = WikiLayer()

def load_wiki() -> str:
    """Helper for legacy components to load the essential context."""
    return wiki_layer.get_essential_context()
