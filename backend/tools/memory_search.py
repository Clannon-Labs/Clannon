"""memory_search tool (key: memory.search) — READ-ONLY recall of the user's memory.

Lets an expert (or the orchestrator) recall relevant prior context MID-task — past
research on a client, earlier decisions, the user's wiki — instead of only what
arrived at hydration. Ranked across all memory tiers + the user's wiki, scoped to
this user, via the MemoryPort's hydrate (injected as `memory`, a MemorySearcher).

READ-ONLY by design: experts never WRITE memory (CLAUDE.md constraint #4 — writes go
through the memory write policy, and the wiki is user-triggered only). This tool only
reads. `wants_memory=True`, so the handler injects the scoped searcher; this module
imports only `registry` + foundation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from foundation import PermissionLevel

from registry import tool


class MemSearchIn(BaseModel):
    query: str = Field(
        description="What to recall from the user's memory + wiki — a question, topic, "
        "client name, or task description. The most relevant memories are returned."
    )
    max_results: int = Field(
        default=8, ge=1, le=20, description="Maximum number of memories to return."
    )


class MemHit(BaseModel):
    store: str          # which tier: wiki / semantic / episodic / procedural
    content: str
    score: float        # per-query relevance
    trust: int          # higher = more authoritative (wiki outranks inferred)


class MemSearchOut(BaseModel):
    hits: list[MemHit]
    degraded: bool      # True when memory was temporarily unavailable (store/embeddings down)
    note: str = ""      # a short explanation when degraded or empty


@tool
class MemorySearchTool:
    name = "search"
    domain = "memory"
    description = (
        "Search the user's memory and wiki for relevant prior context — facts learned "
        "before, past tasks and decisions, preferences, and the user's own knowledge base. "
        "Read-only and scoped to this user. Use it mid-task to recall what you already know "
        "about a client or topic instead of assuming or starting from scratch."
    )
    input_schema = MemSearchIn
    output_schema = MemSearchOut
    permission = PermissionLevel.READ
    wants_memory = True
    tags = ("memory", "recall", "read")

    async def run(self, args: MemSearchIn, memory) -> MemSearchOut:
        pkg = await memory.search(args.query)
        hits = [
            MemHit(store=item.store.value, content=item.content, score=item.score, trust=item.trust)
            for item in pkg.items[: args.max_results]
        ]
        if pkg.degraded:
            note = pkg.notes or "memory temporarily unavailable"
        elif not hits:
            note = "no relevant memory found for this user yet"
        else:
            note = ""
        return MemSearchOut(hits=hits, degraded=pkg.degraded, note=note)
