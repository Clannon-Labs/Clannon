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
    score: float = 0.0          # per-query relevance (rank_score = cosine × recency)
    trust: int = 0              # higher = more authoritative (wiki > inferred)
    created_at: float = 0.0     # unix ts the memory was written; 0 = unknown (wiki)
    # Provenance fields — surfaced from the store payload (additive read-path only).
    # All fields below are already written by store.upsert; they are now propagated
    # through the retrieval path so consumers can explain "why / where" per item.
    rationale: str = ""         # why this was stored (write-time reason)
    confidence: float = 0.0     # write-time confidence (0–1)
    session_id: str = ""        # originating session; "" for wiki / unknown
    trace_id: str = ""          # originating trace; "" when not plumbed at write time
    # SOURCE-DOCUMENT ATTRIBUTION is NOT-YET: no source-document field exists in
    # the current store payload. Gated on issue #16 (typed-record schema).


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
    # User-authored wiki entries (title, content), supplied by the delivery
    # layer that owns wiki storage. Wiki is kept as TEXT (not embedded): the
    # manager selects the relevant ones by text overlap at hydration, as the
    # highest-trust tier. Empty when the caller has no wiki to offer.
    wiki: tuple[tuple[str, str], ...] = ()

    @staticmethod
    def _wiki_pairs(entries: object) -> tuple[tuple[str, str], ...]:
        """(title, content) pairs from a context's `wiki_entries`, skipping any
        non-dict noise. The single place wiki entries are shaped for hydration."""
        return tuple(
            (e.get("title", ""), e.get("content", ""))
            for e in (entries or [])  # type: ignore[union-attr]
            if isinstance(e, dict)
        )

    @classmethod
    def for_turn(cls, ctx: object, normalized: NormalizedInput | None) -> "HydrationRequest":
        """Build a turn's hydration request from a context object + the input to
        search on. THE single source of truth for turning a ctx (`session_id`,
        `user_id`, `wiki_entries`) into the request shape — used by the prefetch
        stage, the orchestrator's serial hydration fallback, and the mid-task
        `memory.search` tool, so the session/user/wiki extraction lives in exactly
        one place. `ctx` is duck-typed (read via `getattr`); foundation imports no
        context type. Callers keep their own guards (e.g. skip when no user_id)."""
        return cls(
            session_id=getattr(ctx, "session_id", "") or "",
            user_id=getattr(ctx, "user_id", "") or "",
            normalized=normalized,
            wiki=cls._wiki_pairs(getattr(ctx, "wiki_entries", None)),
        )


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

    async def learn(
        self,
        user_id: str,
        session_id: str,
        *,
        task: str,
        answer: str,
        findings: list[str],
    ) -> None:
        """Distil durable memory from a completed turn — semantic facts and
        procedural patterns — and persist what's worth keeping. This is the
        background memory-agent (its own LLM call) living behind the door:
        callers hand over the turn, not pre-made proposals. Best-effort; a
        failure here never affects the turn."""
        ...
