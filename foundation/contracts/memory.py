"""
The memory boundary.

Everything the orchestrator and the memory layer agree on, in one place: the
contract dataclasses they exchange, plus the MemoryPort protocol they exchange
them through. Both layers depend only on this shape — neither imports the other.

A port is the contract two layers agree on so neither has to import the other. It
lives here, the nearest common point, precisely so the consumer (orchestrator)
and the implementer (memory manager) stay decoupled. Today MemoryPort is the only
cross-layer port; add others beside it as they appear.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..vocab.types import MemoryStore
from .payloads import NormalizedInput


# ---------------------------------------------------------------------------
# Contracts — the shapes that cross the boundary
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MemoryItem:
    """One retrieved memory, ready to hydrate into orchestrator context."""
    store: MemoryStore
    content: str
    score: float = 0.0          # per-query relevance
    trust: int = 0              # higher = more authoritative (wiki > inferred)


@dataclass(frozen=True, slots=True)
class HydrationRequest:
    """
    What the orchestrator asks the memory manager to hydrate for a turn.

    user_id is the MANDATORY memory scope (every read filters on it);
    session_id is provenance/within-session recall only. allowed_tiers
    lets the caller restrict which tiers are searched (plan gating) —
    None means all tiers.
    """
    session_id: str
    user_id: str = ""
    normalized: NormalizedInput | None = None
    token_budget: int = 0
    allowed_tiers: tuple[MemoryStore, ...] | None = None


@dataclass(slots=True)
class HydrationPackage:
    """
    The memory manager's reply: ranked, budget-bounded context to inject.

    degraded=True means memory was wanted but is temporarily unavailable
    (store down, embeddings down) — distinct from "this user has no memory
    yet". Callers surface degradation honestly; an empty healthy package
    needs no notice.
    """
    items: list[MemoryItem] = field(default_factory=list)
    token_budget: int = 0
    notes: str | None = None
    degraded: bool = False


@dataclass(frozen=True, slots=True)
class MemoryWriteProposal:
    """
    A write the orchestrator/experts PROPOSE after a task. Nothing writes memory
    directly — the memory manager owns whether/where/how a proposal is persisted.
    """
    store: MemoryStore
    content: str
    rationale: str = ""
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Port — the door the contracts cross through
# ---------------------------------------------------------------------------

@runtime_checkable
class MemoryPort(Protocol):
    """
    The ONLY way anything talks to the memory layer.

    The memory manager is the sole implementer; the orchestrator is the sole
    caller (for now). Memory internals (stores, policies, the future background
    memory-agent with its own LLM call) stay behind this door — callers see only
    these two methods.
    """

    async def hydrate(self, request: HydrationRequest) -> HydrationPackage:
        """Return ranked, budget-bounded context to inject before planning."""
        ...

    async def record_write_proposals(
        self, user_id: str, session_id: str, proposals: list[MemoryWriteProposal]
    ) -> None:
        """Hand proposed writes (scoped to a user + session) to the manager; it
        decides whether/where to persist."""
        ...
