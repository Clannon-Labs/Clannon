"""
core/memory/typed_graph.py

Generic MERGE-by-id (nodes) / MERGE-by-connectivity (edges) mechanism shared
by every typed node/edge kind on the Kuzu substrate — lifted out of
`mission_graph_store.py` (LAW 1: two independent copies of this Cypher, one
per domain, is exactly the duplication the law forbids; `mission_graph_store.
py`'s own docstring already flagged this generalization as a "reasonable
future cleanup"). `mission_graph_store.py` (Mission/Task) and
`knowledge_store.py` (Entity/Fact/Claim/MediaSegment, a sibling built the same
way) each register their own schema dict and call these functions — the same
adapter/internals relationship `manager.py` now has to `hydration.py`/
`write_policy.py`.

Node-mutation semantics (verified against real Kuzu, ratified as Mission
Engine Q1): `MERGE ... ON MATCH SET` genuinely mutates a matched node's
properties in place. `create_only` fields are set ONLY on first insert
(identity/write-once — a repeat write can never silently change them);
`mutable` fields refresh on every write (a status cursor, no transition
history kept).

Every function is fail-closed on a missing scope/unknown kind and
degrade-never-fail on a store fault, same discipline as `graph_store.py`.
Nothing above `core/memory/` should ever import this file directly — only
the per-domain registration modules (`mission_graph_store.py`,
`knowledge_store.py`) do.
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
class TypedNodeSchema:
    table: str
    create_only: tuple[str, ...]   # identity + write-once fields; set ONLY on first insert
    mutable: tuple[str, ...]       # the in-place-mutation cursor fields


def is_known_kind(schemas: dict[str, TypedNodeSchema], kind: str) -> bool:
    """Whether `kind` has a typed-node schema backing it in the given registry."""
    return kind in schemas


def is_known_edge_kind(edge_tables: dict[str, tuple[str, str]], kind: str) -> bool:
    """Whether `kind` has a typed-edge table backing it in the given registry."""
    return kind in edge_tables


def upsert_typed_nodes(
    schemas: dict[str, TypedNodeSchema], kind: str, rows: list[dict]
) -> list[str]:
    """Generic MERGE-by-id upsert for a typed node table. Each row carries
    'id' plus whatever of the schema's columns it sets. ON CREATE sets
    create_only + mutable (a brand-new node needs everything); ON MATCH sets
    ONLY mutable — a repeat write can never silently change an identity/
    write-once field, only refresh the cursor fields. Returns the ids
    actually applied; empty on an unknown kind, no rows, or a down store —
    never raises."""
    schema = schemas.get(kind)
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


def upsert_typed_edges(
    edge_tables: dict[str, tuple[str, str]], kind: str, rows: list[dict]
) -> list[dict]:
    """Generic MERGE-by-connectivity edge upsert for a typed rel table.
    Same 'asserted always wins' protection and 'no phantom writes'
    discipline as node upserts: returns the rows actually applied, empty on
    an unknown kind, no rows, or a down store."""
    entry = edge_tables.get(kind)
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


def delete_user(schemas: dict[str, TypedNodeSchema], user_id: str) -> None:
    """Erase every node (and incident edges, via DETACH DELETE) for a user,
    across every typed-node table in `schemas` — right-to-erasure for
    whichever domain owns this schema registry. No-op on a missing user_id
    or a down store; a fault on one table is logged and does not stop the
    others from being purged."""
    if not user_id:
        return
    conn = graph_store.connection()
    if conn is None:
        return
    for schema in schemas.values():
        try:
            conn.execute(f"MATCH (n:{schema.table} {{user_id: $user_id}}) DETACH DELETE n", {"user_id": user_id})
        except Exception as exc:
            log.warning("kuzu delete_user failed (%s): %s", schema.table, exc)


def typed_members(
    schemas: dict[str, TypedNodeSchema], kind: str, scope: GraphScope, *, parent_id: str = ""
) -> GraphReadResult:
    """Every node of `kind` in scope — a complete, deterministic filter-read
    (never ranked, never hop-bounded; not a traversal), optionally restricted
    to one parent's children via a `mission_id`-style property (present only
    on schemas that carry it). Fail-closed on a missing scope/unknown kind;
    degrades on a store fault."""
    schema = schemas.get(kind)
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


def typed_edges_of(
    edge_tables: dict[str, tuple[str, str]], kind: str, scope: GraphScope, node_id: str
) -> GraphReadResult:
    """Every edge of `kind` incident to `node_id`, either direction — a
    complete, deterministic filter-read (never a traversal, never hop-
    bounded), the edge counterpart to `typed_members()`. Fail-closed on a
    missing scope/unknown kind; degrades on a store fault. Rows are
    `{"src", "dst", "origin"}` dicts (not node property dicts —
    `GraphReadResult.rows` is a generic typed-dict shape, shared with
    `typed_members()`'s node rows)."""
    entry = edge_tables.get(kind)
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
