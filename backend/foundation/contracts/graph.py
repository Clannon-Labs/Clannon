"""
The knowledge-graph boundary.

The contract the graph consumer (a code-navigation expert/tool, media extractor,
…) and the graph implementer (`core/memory/graph_manager.GraphManager` over Kuzu)
agree on, so neither imports the other — the same one-door / sole-broker discipline
as `MemoryPort`. No caller ever constructs a raw Cypher query; every read is a
named, purpose-built method on `GraphPort`.

Ratified 2026-07-05 (owner: composite scope; backend: core/memory placement) from
the memory specialist's design proposal. The first slice is code-only (a Python
`ast` import graph); the ENTITY/CLAIM/MEDIA labels + fusion `vector_id` are designed
in for later phases but inert until then — nothing here forces them to be built.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable


class NodeLabel(str, Enum):
    # First slice — code only.
    CODE_FILE = "code_file"
    CODE_MODULE = "code_module"
    # Designed-in for later phases (memory/media fusion) — not built now.
    ENTITY = "entity"
    FACT = "fact"
    CLAIM = "claim"
    MEDIA_SEGMENT = "media_segment"
    # Mission Engine (batch phase) — a mission + its tasks as durable graph nodes.
    # A MISSION's intent/success_criteria are write-once; a TASK's status is a
    # mutable cursor (in-place, no transition history) while non-terminal, asserted
    # once terminal. mission_id lives as a node PROPERTY (a filter under user_id),
    # not a GraphScope dimension — read via members(scope, TASK, parent_id=mission_id).
    MISSION = "mission"
    TASK = "task"


class EdgeLabel(str, Enum):
    IMPORTS = "imports"          # code: A imports B
    DEFINES = "defines"          # code: file defines module/symbol
    # Later phases:
    RELATES_TO = "relates_to"
    CONTRADICTS = "contradicts"
    DERIVED_FROM = "derived_from"
    AUTHORED_BY = "authored_by"
    # Mission Engine (batch phase) — typed task dependencies.
    BLOCKS = "blocks"            # task A blocks task B (B waits on A)
    FEEDS = "feeds"             # task A's output feeds task B
    SUPERSEDES = "supersedes"    # a re-planned task supersedes the one it replaces


class EdgeOrigin(str, Enum):
    """Asserted/inferred typing (mirrors CB1's fact/assumption axis for structure).
    ASSERTED (user-authored) edges are immutable to agents and win on conflict — the
    graph expression of the existing wiki-beats-all trust rule (§I.4)."""
    ASSERTED = "asserted"       # user-authored; agents cannot modify or delete
    INFERRED = "inferred"       # agent-derived; e.g. a parsed import edge


@dataclass(frozen=True, slots=True)
class GraphScope:
    """Mandatory, fail-closed scope — no query is constructed without one; a missing
    scope returns an empty degraded result, same discipline as `HydrationRequest.user_id`.

    `user_id` is PRIMARY, mandatory, and fail-closed (invariant §V.20 unchanged).
    `repo_id` is an OPTIONAL sub-filter AND-ed *under* `user_id` — never a scope on its
    own, never a `user_id` bypass. `repo_id=""` = the user's default/only repo (so a
    user_id-only scope is a strict subset). Both ids enter from trusted `ctx`, never
    from model output (identity-set-once). Clannon's own repo gets an explicit fixed
    scope, never an absent-scope shortcut.
    """
    user_id: str
    repo_id: str = ""


@dataclass(frozen=True, slots=True)
class GraphNode:
    node_id: str                # stable id, e.g. hash(scope, label, natural_key)
    label: NodeLabel
    scope: GraphScope           # mandatory, fail-closed
    properties: dict = field(default_factory=dict)  # label-specific: {"path": …} for CODE_FILE
    vector_id: str = ""          # node<->vector pointer; "" until the memory-fusion phase


@dataclass(frozen=True, slots=True)
class GraphEdge:
    src_id: str
    dst_id: str
    label: EdgeLabel
    origin: EdgeOrigin = EdgeOrigin.INFERRED
    properties: dict = field(default_factory=dict)


@dataclass(slots=True)
class GraphResult:
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    degraded: bool = False      # graph store down/disabled — never raise; mirror
                                # HydrationPackage.degraded (empty-because-down vs -no-edges)
    notes: str = ""


@runtime_checkable
class GraphPort(Protocol):
    """The ONLY way anything talks to the graph layer; `GraphManager` is the sole
    implementer. No raw Cypher crosses this door — every read is a named, purpose-built
    method, exactly as `MemoryPort` exposes `hydrate`/`search`, never a raw Qdrant filter.
    Every method takes a mandatory `GraphScope` and is fail-closed on a missing scope +
    degrade-never-fail on a store fault (returns `GraphResult(degraded=True)`)."""

    async def depends_on(
        self, scope: GraphScope, node_id: str, *, max_hops: int = 1
    ) -> GraphResult:
        """Outgoing edges from node_id — what X needs. max_hops=1 = direct deps;
        >1 = transitive (bounded by a hop ceiling, never an unbounded walk)."""
        ...

    async def dependents_of(
        self, scope: GraphScope, node_id: str, *, max_hops: int = 1
    ) -> GraphResult:
        """Incoming edges to node_id — what needs X. Inverse of depends_on."""
        ...

    async def breaks_if_removed(self, scope: GraphScope, node_id: str) -> GraphResult:
        """Transitive closure of dependents_of — every node whose import chain would
        break if node_id disappeared. Hop-bounded (a dense/cyclic graph can't hang the door)."""
        ...

    async def lookup(
        self, scope: GraphScope, *, label: NodeLabel | None = None,
        vector_id: str = "", natural_key: str = "",
    ) -> GraphResult:
        """POINT lookup of ONE node — requires a `vector_id` (the node<->vector hop, inert
        until the fusion phase) or a label-specific `natural_key` (e.g. a file path). `label`
        ALONE is NOT a bulk read — it returns empty by construction. The bulk "every node of a
        label in scope" read (`members()`, the Mission Engine's "all tasks for mission X") is
        added to this Protocol together with its GraphManager implementer — placing it here
        before that would break the sole implementer's `isinstance(GraphPort)` check."""
        ...

    async def members(
        self, scope: GraphScope, label: NodeLabel, *, parent_id: str = ""
    ) -> GraphResult:
        """BULK read: every node of `label` in scope — the Mission Engine's "all tasks for
        mission X". `parent_id` is an OPTIONAL property filter AND-ed under the scope (for
        TASK it is the `mission_id`; "" = no parent filter, every node of the label in scope).
        Unlike `lookup()`, a bare `label` here IS a bulk read — this is the one place that
        walks all nodes of a kind. Fail-closed on a missing scope, degrade-never-fail on a
        store fault, and empty (not degraded) for a label with no bulk backing. Landed on
        `GraphManager` first (a superset of this Protocol) so this declaration keeps the sole
        implementer's `isinstance(GraphPort)` check green."""
        ...

    async def write(
        self, scope: GraphScope, nodes: list[GraphNode], edges: list[GraphEdge]
    ) -> GraphResult:
        """The sole write path. Batch upsert. A NODE's properties mutate IN PLACE on a repeat
        write to the same `node_id` (verified against Kuzu's `MERGE ... ON MATCH SET` — the
        Mission Engine relies on this for a TASK's mutable `status`; no transition history is
        kept, by design). INFERRED edges may be superseded by a later batch; ASSERTED edges are
        immutable to this call (the manager no-ops/rejects an overwrite rather than silently
        accepting it). Returns what was actually persisted — the same 'no phantom writes'
        discipline as `record_write_proposals`."""
        ...
