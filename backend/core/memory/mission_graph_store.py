"""
core/memory/mission_graph_store.py

Mission Engine (batch phase) — typed nodes (Mission/Task) + typed edges
(Blocks/Feeds/Supersedes) over the SAME embedded Kuzu db `graph_store.py`
owns (shared via `graph_store.connection()`, never a second `kuzu.Database()`
handle on the same path — Kuzu is single-writer/embedded, unlike Qdrant's
client-server model where a second client is merely wasteful, not risky).

This file is a THIN schema registration over `typed_graph.py`'s generic
MERGE-by-id/MERGE-by-connectivity mechanism (split out 2026-07-06, LAW 1: the
mechanism itself used to live here, hardcoded to this module's schema dict;
lifted so `knowledge_store.py` — the Entity/Fact/Claim/MediaSegment sibling —
doesn't need a second copy of the same Cypher). Same adapter/internals
relationship `manager.py` has to `hydration.py`/`write_policy.py`.

`mission_id` lives as a plain node PROPERTY (ratified Q2) — a filter under
`user_id`, not a `GraphScope` dimension — so `typed_members()` is a complete,
deterministic filter-read, never a traversal.

`GraphManager` (not this module) is the sole `GraphPort`-facing caller;
nothing above `core/memory/` should ever import this file directly.
"""
from __future__ import annotations

from foundation import GraphScope

from . import typed_graph
from .graph_store import GraphReadResult
from .typed_graph import TypedNodeSchema

_TYPED_NODE_SCHEMAS: dict[str, TypedNodeSchema] = {
    "mission": TypedNodeSchema(
        "Mission",
        create_only=("user_id", "repo_id", "mission_id", "intent", "success_criteria"),
        mutable=("status", "updated_at"),
    ),
    "task": TypedNodeSchema(
        "Task",
        create_only=("user_id", "repo_id", "task_id", "mission_id"),
        mutable=("summary", "status", "evidence", "updated_at"),
    ),
}

# Edge kind -> (rel table, endpoint node table). Both current edges are
# Task-to-Task; a future kind naming a different endpoint table is a one-line
# addition here, not a new function.
_TYPED_EDGE_TABLES: dict[str, tuple[str, str]] = {
    "blocks": ("Blocks", "Task"),
    "feeds": ("Feeds", "Task"),
    "supersedes": ("Supersedes", "Task"),
}


def is_known_kind(kind: str) -> bool:
    """Whether `kind` (a NodeLabel.value string, e.g. "mission"/"task") has a
    typed-node schema backing it — lets `graph_manager.py` give an honest
    "not yet backed by a table" note without reaching into this module's
    schema dict directly."""
    return typed_graph.is_known_kind(_TYPED_NODE_SCHEMAS, kind)


def is_known_edge_kind(kind: str) -> bool:
    """Whether `kind` (an EdgeLabel.value string, e.g. "blocks"/"feeds") has a
    typed-edge table backing it — the `edges_of()` counterpart to
    `is_known_kind`."""
    return typed_graph.is_known_edge_kind(_TYPED_EDGE_TABLES, kind)


def upsert_typed_nodes(kind: str, rows: list[dict]) -> list[str]:
    return typed_graph.upsert_typed_nodes(_TYPED_NODE_SCHEMAS, kind, rows)


def upsert_typed_edges(kind: str, rows: list[dict]) -> list[dict]:
    return typed_graph.upsert_typed_edges(_TYPED_EDGE_TABLES, kind, rows)


def delete_user(user_id: str) -> None:
    """Erase every Mission/Task node (and incident Blocks/Feeds/Supersedes
    edges) for a user — the Mission Engine's half of right-to-erasure,
    parallel to `graph_store.delete_user`'s CodeFile purge."""
    typed_graph.delete_user(_TYPED_NODE_SCHEMAS, user_id)


def typed_members(kind: str, scope: GraphScope, *, parent_id: str = "") -> GraphReadResult:
    """Every node of `kind` in scope — backs `GraphPort.members()`."""
    return typed_graph.typed_members(_TYPED_NODE_SCHEMAS, kind, scope, parent_id=parent_id)


def typed_edges_of(kind: str, scope: GraphScope, node_id: str) -> GraphReadResult:
    """Every edge of `kind` incident to `node_id` — backs `GraphPort.edges_of()`."""
    return typed_graph.typed_edges_of(_TYPED_EDGE_TABLES, kind, scope, node_id)
