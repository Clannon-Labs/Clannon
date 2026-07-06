"""
core/memory/knowledge_store.py

The knowledge-web (CB2/CB3/EB3 substrate, ratified 2026-07-06 —
proposals/archive/to-backend/2026-07-06_knowledge-web-design-cb2-cb3-eb3.md):
Entity/Fact/Claim/MediaSegment typed nodes + RelatesTo/Contradicts/
DerivedFrom/AuthoredBy typed edges, over the SAME embedded Kuzu db
`graph_store.py` owns.

A thin schema registration over `typed_graph.py`'s generic mechanism — the
same relationship `mission_graph_store.py` has to it. This module owns no
Cypher of its own beyond the schema dicts; `typed_graph.py`'s generic
functions do the actual MERGE-by-id / MERGE-by-connectivity work.

Node identity (why each schema's `create_only` set is what it is):
- Entity: `canonical_name` (normalized at extraction time) IS the identity —
  two mentions of the same name converge onto the same node by construction,
  no separate resolution step (§1.1 of the ratified design).
- Fact/Claim: keyed by `vector_id`, the originating Qdrant memory point's own
  id — the fusion pointer doubles as the identity key, since each Fact/Claim
  node is the graph twin of exactly one memory point.
- MediaSegment: keyed by a caller-constructed `segment_key` (e.g.
  `f"{source_media_id}:{start_ts}-{end_ts}"`) — a segment's identity is which
  part of which media file, independent of whether it has been embedded yet.

Edge heterogeneity: RelatesTo/DerivedFrom/AuthoredBy span more than one node
type pair (e.g. Entity->Fact and Entity->Claim under one rel table) —
`node_table=None` in `_TYPED_EDGE_TABLES` tells `typed_graph.py` to match by
id/scope without a label constraint (verified against real Kuzu 0.11.3).
Contradicts is homogeneous (Claim-to-Claim only).

`GraphManager` (not this module) is the sole `GraphPort`-facing caller;
nothing above `core/memory/` should ever import this file directly.
"""
from __future__ import annotations

from foundation import GraphScope

from . import typed_graph
from .graph_store import GraphReadResult
from .typed_graph import TypedNodeSchema

_TYPED_NODE_SCHEMAS: dict[str, TypedNodeSchema] = {
    "entity": TypedNodeSchema(
        "Entity",
        create_only=("user_id", "repo_id", "entity_type", "canonical_name"),
        mutable=("vector_id", "updated_at"),
        defaults={"vector_id": "", "updated_at": 0.0},
    ),
    "fact": TypedNodeSchema(
        "Fact",
        create_only=("user_id", "repo_id", "content"),
        mutable=("confidence", "vector_id", "updated_at"),
        defaults={"confidence": 0.0, "vector_id": "", "updated_at": 0.0},
    ),
    "claim": TypedNodeSchema(
        "Claim",
        create_only=("user_id", "repo_id", "content"),
        mutable=("confidence", "vector_id", "updated_at"),
        defaults={"confidence": 0.0, "vector_id": "", "updated_at": 0.0},
    ),
    "media_segment": TypedNodeSchema(
        "MediaSegment",
        create_only=("user_id", "repo_id", "modality", "source_media_id", "start_ts", "end_ts", "text"),
        mutable=("vector_id", "updated_at"),
        defaults={"vector_id": "", "updated_at": 0.0},
    ),
}

# Edge kind -> (rel table, endpoint node table | a tuple of CANDIDATE tables
# for a heterogeneous rel — Kuzu needs a concrete label to MERGE a
# relationship, so a heterogeneous kind's candidates are resolved per-id at
# write time (`typed_graph._resolve_node_tables`), not matched label-free).
_TYPED_EDGE_TABLES: dict[str, tuple[str, str | tuple[str, ...]]] = {
    "relates_to": ("RelatesTo", ("Entity", "Fact", "Claim", "MediaSegment")),
    "contradicts": ("Contradicts", "Claim"),  # homogeneous: Claim<->Claim only
    "derived_from": ("DerivedFrom", ("Entity", "Fact", "Claim", "MediaSegment", "Task")),
    "authored_by": ("AuthoredBy", ("Fact", "Claim", "Entity")),
}


def is_known_kind(kind: str) -> bool:
    """Whether `kind` (a NodeLabel.value string, e.g. "entity"/"fact") has a
    typed-node schema backing it — lets `graph_manager.py` give an honest
    "not yet backed by a table" note without reaching into this module's
    schema dict directly."""
    return typed_graph.is_known_kind(_TYPED_NODE_SCHEMAS, kind)


def is_known_edge_kind(kind: str) -> bool:
    """Whether `kind` (an EdgeLabel.value string, e.g. "relates_to") has a
    typed-edge table backing it — the `edges_of()` counterpart to
    `is_known_kind`."""
    return typed_graph.is_known_edge_kind(_TYPED_EDGE_TABLES, kind)


def upsert_typed_nodes(kind: str, rows: list[dict]) -> list[str]:
    return typed_graph.upsert_typed_nodes(_TYPED_NODE_SCHEMAS, kind, rows)


def upsert_typed_edges(kind: str, rows: list[dict]) -> list[dict]:
    return typed_graph.upsert_typed_edges(_TYPED_EDGE_TABLES, kind, rows)


def delete_user(user_id: str) -> None:
    """Erase every Entity/Fact/Claim/MediaSegment node (and incident edges)
    for a user — the knowledge web's half of right-to-erasure, parallel to
    `graph_store.delete_user`/`mission_graph_store.delete_user`."""
    typed_graph.delete_user(_TYPED_NODE_SCHEMAS, user_id)


def typed_members(kind: str, scope: GraphScope, *, parent_id: str = "") -> GraphReadResult:
    """Every node of `kind` in scope — backs `GraphPort.members()`.
    `parent_id` is accepted for interface parity with `mission_graph_store`
    but has no matching property on any knowledge-web schema today, so it is
    a no-op filter here (the same "" = no parent filter default applies)."""
    return typed_graph.typed_members(_TYPED_NODE_SCHEMAS, kind, scope, parent_id=parent_id)


def typed_edges_of(kind: str, scope: GraphScope, node_id: str) -> GraphReadResult:
    """Every edge of `kind` incident to `node_id` — backs `GraphPort.edges_of()`."""
    return typed_graph.typed_edges_of(_TYPED_EDGE_TABLES, kind, scope, node_id)
