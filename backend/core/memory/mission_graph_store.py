"""
core/memory/mission_graph_store.py

Mission Engine (batch phase) — typed nodes (Mission/Task) + typed edges
(Blocks/Feeds/Supersedes) over the SAME embedded Kuzu db `graph_store.py`
owns (shared via `graph_store.connection()`, never a second `kuzu.Database()`
handle on the same path — Kuzu is single-writer/embedded, unlike Qdrant's
client-server model where a second client is merely wasteful, not risky).

A sibling to `graph_store.py`, not an addition to it: `graph_store.py` is
scoped to the CB2 code-import graph (CodeFile/IMPORTS) and was already near
the LAW-2 file-size ceiling; this file owns the Mission Engine's own tables,
generic over a small per-"kind" schema rather than a CodeFile-shaped function
per label (`graph_manager.py`'s `write()` was hardcoding one property name,
`path`, into a fixed row shape — the memory specialist's Q1/Q2 answers to
orchestration's Mission Engine questions, ratified 2026-07-05). CodeFile's own
`upsert_nodes`/`upsert_edges` are untouched (stable, tested, low-risk-to-not-
touch); unifying them onto this same generic mechanism is a reasonable future
cleanup, not required for this addition.

Node-mutation semantics (verified against real Kuzu, ratified as Q1):
`MERGE ... ON MATCH SET` genuinely mutates a matched node's properties in
place — a TASK's non-terminal `status` is a mutable CURSOR (no transition
history kept; `SUPERSEDES` carries re-plan history, not status churn).
`mission_id` lives as a plain node PROPERTY (ratified Q2) — a filter under
`user_id`, not a `GraphScope` dimension — so `typed_members()` is a complete,
deterministic filter-read, never a traversal.

`GraphManager` (not this module) is the sole `GraphPort`-facing caller;
nothing above `core/memory/` should ever import this file directly.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from foundation import GraphScope

from . import graph_store
from .graph_store import GraphReadResult

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class _TypedNodeSchema:
    table: str
    create_only: tuple[str, ...]   # identity + write-once fields; set ONLY on first insert
    mutable: tuple[str, ...]       # the Q1-verified in-place-mutation cursor fields


_TYPED_NODE_SCHEMAS: dict[str, _TypedNodeSchema] = {
    "mission": _TypedNodeSchema(
        "Mission",
        create_only=("user_id", "repo_id", "mission_id", "intent", "success_criteria"),
        mutable=("status", "updated_at"),
    ),
    "task": _TypedNodeSchema(
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
    return kind in _TYPED_NODE_SCHEMAS


def is_known_edge_kind(kind: str) -> bool:
    """Whether `kind` (an EdgeLabel.value string, e.g. "blocks"/"feeds") has a
    typed-edge table backing it — the `edges_of()` counterpart to
    `is_known_kind`."""
    return kind in _TYPED_EDGE_TABLES


def upsert_typed_nodes(kind: str, rows: list[dict]) -> list[str]:
    """Generic MERGE-by-id upsert for a typed node table (Mission/Task today;
    any future typed label the same way). Each row carries 'id' plus whatever
    of the schema's columns it sets. ON CREATE sets create_only + mutable
    (a brand-new node needs everything); ON MATCH sets ONLY mutable — a
    repeat write can never silently change an identity/write-once field
    (mission_id, intent, …), only refresh the cursor fields (status, …).
    Returns the ids actually applied; empty on an unknown kind, no rows, or a
    down store — never raises."""
    schema = _TYPED_NODE_SCHEMAS.get(kind)
    if schema is None:
        log.warning("upsert_typed_nodes: unknown kind %r", kind)
        return []
    conn = graph_store.connection()
    if conn is None or not rows:
        return []
    on_create = ", ".join(f"n.{c} = r.{c}" for c in (*schema.create_only, *schema.mutable))
    on_match = ", ".join(f"n.{c} = r.{c}" for c in schema.mutable)
    try:
        conn.execute(
            f"UNWIND $rows AS r MERGE (n:{schema.table} {{id: r.id}}) "
            f"ON CREATE SET {on_create} ON MATCH SET {on_match}",
            {"rows": rows},
        )
        return [r["id"] for r in rows]
    except Exception as exc:
        log.warning("kuzu typed-node upsert failed (%s): %s", kind, exc)
        return []


def upsert_typed_edges(kind: str, rows: list[dict]) -> list[dict]:
    """Generic MERGE-by-connectivity edge upsert for a typed rel table
    (Task-to-Task Blocks/Feeds/Supersedes) — parallel to `graph_store.
    upsert_edges`' CodeFile/IMPORTS-specific path. Same 'asserted always
    wins' protection and 'no phantom writes' discipline: returns the rows
    actually applied, empty on an unknown kind, no rows, or a down store."""
    entry = _TYPED_EDGE_TABLES.get(kind)
    if entry is None:
        log.warning("upsert_typed_edges: unknown kind %r", kind)
        return []
    rel_table, node_table = entry
    conn = graph_store.connection()
    if conn is None or not rows:
        return []
    try:
        protected = conn.execute(
            f"UNWIND $rows AS e MATCH (s:{node_table} {{id: e.src}})-[r:{rel_table}]->"
            f"(d:{node_table} {{id: e.dst}}) WHERE r.origin = 'asserted' RETURN e.src, e.dst",
            {"rows": rows},
        )
        protected_pairs = {(r[0], r[1]) for r in protected.get_all()}
        candidates = [r for r in rows if (r["src"], r["dst"]) not in protected_pairs]
        if not candidates:
            return []
        conn.execute(
            f"UNWIND $rows AS e MATCH (s:{node_table} {{id: e.src}}), (d:{node_table} {{id: e.dst}}) "
            f"MERGE (s)-[r:{rel_table}]->(d) ON CREATE SET r.origin = e.origin "
            "ON MATCH SET r.origin = e.origin",
            {"rows": candidates},
        )
        applied = conn.execute(
            f"UNWIND $rows AS e MATCH (s:{node_table} {{id: e.src}})-[r:{rel_table}]->"
            f"(d:{node_table} {{id: e.dst}}) RETURN e.src, e.dst",
            {"rows": candidates},
        )
        applied_pairs = {(r[0], r[1]) for r in applied.get_all()}
        return [r for r in candidates if (r["src"], r["dst"]) in applied_pairs]
    except Exception as exc:
        log.warning("kuzu typed-edge upsert failed (%s): %s", kind, exc)
        return []


def delete_user(user_id: str) -> None:
    """Erase every Mission/Task node (and incident Blocks/Feeds/Supersedes
    edges, via DETACH DELETE) for a user — the Mission Engine's half of
    right-to-erasure, parallel to `graph_store.delete_user`'s CodeFile purge.
    Iterates every known typed-node table rather than hardcoding
    Mission/Task by name, so a future typed kind added to
    `_TYPED_NODE_SCHEMAS` is covered automatically. No-op on a missing
    user_id or a down store; a fault on one table is logged and does not
    stop the others from being purged."""
    if not user_id:
        return
    conn = graph_store.connection()
    if conn is None:
        return
    for schema in _TYPED_NODE_SCHEMAS.values():
        try:
            conn.execute(f"MATCH (n:{schema.table} {{user_id: $user_id}}) DETACH DELETE n", {"user_id": user_id})
        except Exception as exc:
            log.warning("kuzu delete_user failed (%s): %s", schema.table, exc)


def typed_members(kind: str, scope: GraphScope, *, parent_id: str = "") -> GraphReadResult:
    """Every node of `kind` in scope — a complete, deterministic filter-read
    (never ranked, never hop-bounded; not a traversal), optionally restricted
    to one parent's children via the mission_id property (e.g. every task
    under one mission). Backs `GraphPort.members()`. Fail-closed on a missing
    scope/unknown kind; degrades on a store fault, matching every other read
    in this package."""
    schema = _TYPED_NODE_SCHEMAS.get(kind)
    if not scope.user_id or schema is None:
        return GraphReadResult(degraded=True, notes="missing user_id or unknown kind — refused, fail-closed")
    conn = graph_store.connection()
    if conn is None:
        return GraphReadResult(degraded=True, notes="graph store unavailable")
    columns = ("id", *schema.create_only, *schema.mutable)
    return_clause = ", ".join(f"n.{c}" for c in columns)
    params: dict[str, Any] = {"user_id": scope.user_id, "repo_id": scope.repo_id}
    where = "n.user_id = $user_id AND n.repo_id = $repo_id"
    if parent_id and "mission_id" in columns:
        where += " AND n.mission_id = $parent_id"
        params["parent_id"] = parent_id
    try:
        result = conn.execute(f"MATCH (n:{schema.table}) WHERE {where} RETURN {return_clause}", params)
        rows = tuple(dict(zip(columns, row)) for row in result.get_all())
        return GraphReadResult(rows=rows)
    except Exception as exc:
        log.warning("kuzu typed-members read failed (%s): %s", kind, exc)
        return GraphReadResult(degraded=True, notes="graph store unavailable")


def typed_edges_of(kind: str, scope: GraphScope, node_id: str) -> GraphReadResult:
    """Every edge of `kind` incident to `node_id`, either direction — a
    complete, deterministic filter-read (never a traversal, never hop-
    bounded), the edge counterpart to `typed_members()`. Backs
    `GraphPort.edges_of()` — the fix for the TASK-edge read gap orchestration
    flagged (BLOCKS/FEEDS/SUPERSEDES could be written via `write()` but never
    read back). Fail-closed on a missing scope/unknown kind; degrades on a
    store fault. Rows are `{"src", "dst", "origin"}` dicts (not node property
    dicts — `GraphReadResult.rows` is a generic typed-dict shape, shared with
    `typed_members()`'s node rows)."""
    entry = _TYPED_EDGE_TABLES.get(kind)
    if not scope.user_id or entry is None:
        return GraphReadResult(degraded=True, notes="missing user_id or unknown kind — refused, fail-closed")
    rel_table, node_table = entry
    conn = graph_store.connection()
    if conn is None:
        return GraphReadResult(degraded=True, notes="graph store unavailable")
    params = {"user_id": scope.user_id, "repo_id": scope.repo_id, "node_id": node_id}
    try:
        result = conn.execute(
            f"MATCH (a:{node_table})-[r:{rel_table}]->(b:{node_table}) "
            "WHERE a.user_id = $user_id AND a.repo_id = $repo_id "
            "AND b.user_id = $user_id AND b.repo_id = $repo_id "
            "AND (a.id = $node_id OR b.id = $node_id) "
            "RETURN a.id, b.id, r.origin",
            params,
        )
        rows = tuple({"src": r[0], "dst": r[1], "origin": r[2]} for r in result.get_all())
        return GraphReadResult(rows=rows)
    except Exception as exc:
        log.warning("kuzu typed-edges-of read failed (%s): %s", kind, exc)
        return GraphReadResult(degraded=True, notes="graph store unavailable")
