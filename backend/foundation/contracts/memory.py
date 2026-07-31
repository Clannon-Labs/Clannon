"""
The memory boundary.

Everything pipeline/delivery and memory layer agree on: neutral contract
dataclasses plus MemoryPort protocol. Consumers never import memory internals.

A port is the contract two layers agree on so neither has to import the other. It
lives here, the nearest common point, precisely so pipeline/delivery consumers
and Memory Manager stay decoupled. Today MemoryPort is the only
cross-layer port; add others beside it as they appear.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..vocab.types import MemoryKind, MemorySaver, MemoryStore
from .payloads import NormalizedInput


# ---------------------------------------------------------------------------
# Contracts — the shapes that cross the boundary
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MemoryItem:
    """One retrieved item, ready for pipeline-prepared user context."""
    store: MemoryStore
    content: str
    memory_id: str = ""          # stable store id; empty for wiki / legacy synthetic items
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
    saved_by: MemorySaver = MemorySaver.UNSPECIFIED
                                # trusted component that caused persistence
    # Typed-knowledge (CB1) — additive; UNSPECIFIED/0.0/"" preserve legacy behaviour.
    kind: MemoryKind = MemoryKind.UNSPECIFIED  # fact vs assumption; UNSPECIFIED = untyped/legacy
    valid_at: float = 0.0        # unix ts the fact became true (vs created_at = when learned); 0 = unknown
    source: str = ""             # source-document attribution; "" = agent inference (resolves the old NOT-YET)
    superseded_by: str = ""      # memory_id of the record replacing this; "" = current (EB1 sets this — inert in CB1)
    participants: str = ""       # CB4: who was involved in a DECISION record (proposer / discussion
                                 # participants); "" when unknown. Carried, not manufactured — the ADR
                                 # source doesn't record this today; populating it is a docs/orchestration concern


@dataclass(frozen=True, slots=True)
class HydrationRequest:
    """
    What memory-owned prefetch asks Manager to hydrate for a turn.

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
    def wiki_pairs(entries: object) -> tuple[tuple[str, str], ...]:
        """(title, content) pairs from a caller's `wiki_entries`, skipping any
        non-dict noise. THE single place wiki entries are shaped for hydration —
        use it wherever a `HydrationRequest.wiki` is built (turn stages via
        `for_turn`, and direct constructions like the hydration-preview endpoint
        that have no ctx object)."""
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
        stage and authenticated preview delivery, so session/user/wiki extraction
        lives in one place. `ctx` is duck-typed; foundation imports no context type."""
        return cls(
            session_id=getattr(ctx, "session_id", "") or "",
            user_id=getattr(ctx, "user_id", "") or "",
            normalized=normalized,
            wiki=cls.wiki_pairs(getattr(ctx, "wiki_entries", None)),
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
class MemoryTurn:
    """One completed, filter-approved turn handed to the Memory Manager.

    This is neutral evidence, not a storage instruction. Callers do not choose
    tiers or writes; the manager's own curator decides whether anything is worth
    retaining and uses its internal tools behind the sole-broker boundary.
    """
    user_id: str
    session_id: str
    trace_id: str
    request: str
    response: str
    findings: tuple[str, ...] = ()
    decisions: tuple[str, ...] = ()
    participants: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MemoryWriteProposal:
    """
    One internal candidate produced by Memory Manager curator tooling.

    Kept in foundation temporarily for benchmark/tooling compatibility while
    legacy direct-write harnesses migrate. Runtime orchestrators and experts do
    not construct this type; they hand neutral `MemoryTurn` evidence to Manager.
    """
    store: MemoryStore
    content: str
    rationale: str = ""
    confidence: float = 0.0
    kind: MemoryKind = MemoryKind.UNSPECIFIED  # writer sets FACT (source-backed) vs ASSUMPTION (inferred)
    valid_at: float = 0.0   # when the asserted fact became true; 0 = unknown (falls back to write time)
    source: str = ""        # originating document/tool; "" = agent inference
    participants: str = ""  # CB4: who was involved (proposer / discussion participants); "" when unknown


# ---------------------------------------------------------------------------
# Port — the door the contracts cross through
# ---------------------------------------------------------------------------

@runtime_checkable
class MemoryPort(Protocol):
    """
    The ONLY way runtime code talks to memory.

    Memory Manager is sole implementer. Pipeline memory stages call hydration
    and turn curation; authenticated delivery calls bounded list/delete. Memory
    internals, storage, tier decisions, and curator tools stay behind this door.
    """

    async def hydrate(self, request: HydrationRequest) -> HydrationPackage:
        """Return ranked, budget-bounded context to inject before planning."""
        ...

    async def process_turn(self, turn: MemoryTurn) -> list[MemoryItem]:
        """Curate one completed turn. The manager's own LLM chooses no-op vs.
        typed tool actions; callers cannot select tiers or propose writes.
        Returns only entries actually persisted."""
        ...

    async def list_entries(self, user_id: str) -> list[MemoryItem]:
        """Return bounded durable inferred-memory entries for one authenticated
        user. Empty scope or store failure returns an empty list."""
        ...

    async def delete_entry(self, user_id: str, memory_id: str) -> bool:
        """Delete one inferred-memory point only when it belongs to `user_id`.
        Unknown and foreign ids are indistinguishable (`False`)."""
        ...
