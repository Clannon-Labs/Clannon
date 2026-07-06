"""
Graph Manager — the single door to the graph layer (foundation.GraphPort).

Adapts `graph_store.py`'s internal bare-path shapes (`GraphReadResult`, plain
node/edge dicts) to the port's public `GraphNode`/`GraphEdge`/`GraphResult`
objects — the same layering `MemoryManager` has over `store.py`. The first
slice is code-only: only `NodeLabel.CODE_FILE` / `EdgeLabel.IMPORTS` are
backed by a real Kuzu table today. Anything else `write()` is asked to
persist is honestly rejected (surfaced in `notes`), never silently dropped or
pretended to succeed.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from foundation import (
    EdgeLabel,
    GraphEdge,
    GraphNode,
    GraphResult,
    GraphScope,
    NodeLabel,
)

from . import graph_store, mission_graph_store
from .graph_extract import build_code_import_graph

log = logging.getLogger(__name__)

# Mission Engine (batch phase) — which node/edge labels ride the generic
# typed-node/typed-edge path (mission_graph_store.py) instead of CodeFile's
# hardcoded path. The dict's value is BOTH the natural-key property name
# write() reads off GraphNode.properties AND the "kind" string
# mission_graph_store's schema dict is keyed by (NodeLabel.MISSION.value ==
# "mission" == the schema key — no separate mapping needed for that half).
_TYPED_NODE_KEY_PROPERTY: dict[NodeLabel, str] = {
    NodeLabel.MISSION: "mission_id",
    NodeLabel.TASK: "task_id",
}
_TYPED_EDGE_LABELS = frozenset({EdgeLabel.BLOCKS, EdgeLabel.FEEDS, EdgeLabel.SUPERSEDES})


def _parse_node_id(node_id: str) -> tuple[str, str, str] | None:
    """Reverse `graph_store.node_id`'s `user_id|repo_id|path` format.
    maxsplit=2 so a path containing '|' stays intact in the third segment.
    user_id/repo_id themselves never contain '|' — they come from trusted
    ctx (auth-issued ids), not user-controlled text."""
    parts = node_id.split("|", 2)
    if len(parts) != 3:
        return None
    return parts[0], parts[1], parts[2]


def _scope_owns(scope: GraphScope, node_id: str) -> bool:
    """True when node_id's embedded scope matches the operation's
    authoritative scope — defense in depth (mirrors store.py's
    `_owns_point`): a caller can never use a foreign-scoped node_id by
    quoting it under a different scope's call."""
    parsed = _parse_node_id(node_id)
    return parsed is not None and parsed[0] == scope.user_id and parsed[1] == scope.repo_id


def _to_graph_node(scope: GraphScope, path: str) -> GraphNode:
    return GraphNode(
        node_id=graph_store.node_id(scope, path),
        label=NodeLabel.CODE_FILE,
        scope=scope,
        properties={"path": path},
    )


def _from_read(scope: GraphScope, read: graph_store.GraphReadResult) -> GraphResult:
    return GraphResult(
        nodes=[_to_graph_node(scope, p) for p in sorted(read.paths)],
        degraded=read.degraded,
        notes=read.notes,
    )


class GraphManager:
    """Kuzu-backed implementer of foundation.GraphPort."""

    async def depends_on(self, scope: GraphScope, node_id: str, *, max_hops: int = 1) -> GraphResult:
        return await self._read(scope, node_id, lambda s, p: graph_store.depends_on(s, p, max_hops=max_hops))

    async def dependents_of(self, scope: GraphScope, node_id: str, *, max_hops: int = 1) -> GraphResult:
        return await self._read(scope, node_id, lambda s, p: graph_store.dependents_of(s, p, max_hops=max_hops))

    async def breaks_if_removed(self, scope: GraphScope, node_id: str) -> GraphResult:
        return await self._read(scope, node_id, graph_store.breaks_if_removed)

    async def lookup(
        self, scope: GraphScope, *, label: NodeLabel | None = None,
        vector_id: str = "", natural_key: str = "",
    ) -> GraphResult:
        if not scope.user_id:
            return GraphResult(degraded=True, notes="missing user_id — refused, fail-closed")
        if vector_id:
            # designed-in for the memory/media fusion phase; nothing sets a
            # vector_id yet, so this is honestly always empty, not degraded.
            return GraphResult(notes="vector_id lookup is inert until the memory-fusion phase")
        if not natural_key or label not in (None, NodeLabel.CODE_FILE):
            return GraphResult()
        read = await asyncio.to_thread(graph_store.lookup_by_path, scope, natural_key)
        return _from_read(scope, read)

    async def _read(self, scope: GraphScope, node_id: str, fn) -> GraphResult:
        if not scope.user_id:
            return GraphResult(degraded=True, notes="missing user_id — refused, fail-closed")
        # Store-down must win over an id-shape judgment: "unavailable" is
        # true independent of what was asked, so check it BEFORE deciding
        # whether node_id even parses/belongs to this scope. Otherwise a
        # down store + a malformed/foreign id silently reads as a healthy
        # empty result instead of the degraded one the caller needs to see.
        if await asyncio.to_thread(graph_store.is_down):
            return GraphResult(degraded=True, notes="graph store unavailable")
        parsed = _parse_node_id(node_id)
        if parsed is None or not _scope_owns(scope, node_id):
            # Not a fault — a node_id that doesn't parse or belongs to
            # another scope is a normal empty result, same as a memory query
            # that finds nothing. Silent-empty, never a signal about whether
            # a foreign scope's node exists (no tenant-existence oracle).
            return GraphResult()
        _, _, path = parsed
        read = await asyncio.to_thread(fn, scope, path)
        return _from_read(scope, read)

    async def write(
        self, scope: GraphScope, nodes: list[GraphNode], edges: list[GraphEdge]
    ) -> GraphResult:
        if not scope.user_id:
            return GraphResult(degraded=True, notes="missing user_id — refused, fail-closed")
        if await asyncio.to_thread(graph_store.is_down):
            return GraphResult(degraded=True, notes="graph store unavailable")

        notes: list[str] = []
        code_file_rows: list[dict] = []
        typed_node_rows: dict[str, list[dict]] = {}
        accepted_nodes: list[GraphNode] = []
        for n in nodes:
            if n.scope != scope:
                notes.append("node scope did not match the write's scope — refused")
                continue
            if n.label == NodeLabel.CODE_FILE:
                path = n.properties.get("path", "")
                if not path:
                    notes.append("CODE_FILE node missing a path property — refused")
                    continue
                code_file_rows.append(
                    {"id": graph_store.node_id(scope, path), "user_id": scope.user_id,
                     "repo_id": scope.repo_id, "path": path}
                )
            elif n.label in _TYPED_NODE_KEY_PROPERTY:
                key_prop = _TYPED_NODE_KEY_PROPERTY[n.label]
                natural_key = n.properties.get(key_prop, "")
                if not natural_key:
                    notes.append(f"{n.label.value} node missing a {key_prop} property — refused")
                    continue
                # caller-supplied properties spread FIRST so the manager-computed
                # id/user_id/repo_id always win — a caller can never clobber its
                # own row's identity by naming one of those keys in `properties`.
                row = {
                    **n.properties, "id": graph_store.node_id(scope, natural_key),
                    "user_id": scope.user_id, "repo_id": scope.repo_id,
                }
                typed_node_rows.setdefault(n.label.value, []).append(row)
            else:
                notes.append(f"label {n.label.value!r} not yet backed by a table — dropped")
                continue
            accepted_nodes.append(n)

        applied_node_ids: set[str] = set()
        if code_file_rows:
            applied_node_ids |= set(await asyncio.to_thread(graph_store.upsert_nodes, scope, code_file_rows))
        for kind, rows in typed_node_rows.items():
            applied_node_ids |= set(
                await asyncio.to_thread(mission_graph_store.upsert_typed_nodes, kind, rows)
            )

        imports_edge_rows: list[dict] = []
        typed_edge_rows: dict[str, list[dict]] = {}
        edge_by_pair: dict[tuple[str, str], GraphEdge] = {}
        for e in edges:
            if not (_scope_owns(scope, e.src_id) and _scope_owns(scope, e.dst_id)):
                notes.append("edge endpoint outside this scope — refused")
                continue
            if e.label == EdgeLabel.IMPORTS:
                imports_edge_rows.append({"src": e.src_id, "dst": e.dst_id, "origin": e.origin.value})
            elif e.label in _TYPED_EDGE_LABELS:
                typed_edge_rows.setdefault(e.label.value, []).append(
                    {"src": e.src_id, "dst": e.dst_id, "origin": e.origin.value}
                )
            else:
                notes.append(f"edge label {e.label.value!r} not yet backed by a table — dropped")
                continue
            edge_by_pair[(e.src_id, e.dst_id)] = e

        applied_edges: list[GraphEdge] = []
        if imports_edge_rows:
            applied_rows = await asyncio.to_thread(graph_store.upsert_edges, scope, imports_edge_rows)
            applied_edges.extend(edge_by_pair[(r["src"], r["dst"])] for r in applied_rows)
        for kind, rows in typed_edge_rows.items():
            applied_rows = await asyncio.to_thread(mission_graph_store.upsert_typed_edges, kind, rows)
            applied_edges.extend(edge_by_pair[(r["src"], r["dst"])] for r in applied_rows)

        return GraphResult(
            nodes=[n for n in accepted_nodes if n.node_id in applied_node_ids],
            edges=applied_edges,
            notes="; ".join(notes),
        )

    async def members(
        self, scope: GraphScope, label: NodeLabel, *, parent_id: str = ""
    ) -> GraphResult:
        """Every node of `label` in scope — the Mission Engine's "all tasks for
        mission X" (ratified 2026-07-05: mission_id is a node PROPERTY filter,
        not a GraphScope dimension). NOT on the GraphPort Protocol yet — this
        method exists on GraphManager first (a superset of the Protocol, so
        isinstance stays green) so the backend-agent can add it to the
        Protocol same-day without breaking the sole implementer check."""
        if not scope.user_id:
            return GraphResult(degraded=True, notes="missing user_id — refused, fail-closed")
        if await asyncio.to_thread(graph_store.is_down):
            return GraphResult(degraded=True, notes="graph store unavailable")
        kind = label.value
        if not mission_graph_store.is_known_kind(kind):
            return GraphResult(notes=f"label {label.value!r} has no bulk members() backing")
        read = await asyncio.to_thread(mission_graph_store.typed_members, kind, scope, parent_id=parent_id)
        if read.degraded:
            return GraphResult(degraded=True, notes=read.notes)
        nodes = [
            GraphNode(node_id=row["id"], label=label, scope=scope,
                      properties={k: v for k, v in row.items() if k not in ("id", "user_id", "repo_id")})
            for row in read.rows
        ]
        return GraphResult(nodes=nodes, notes=read.notes)

    # ---- build-slice surface (not part of GraphPort) ---------------------

    async def build_code_graph(self, scope: GraphScope, root: Path) -> GraphResult:
        """Rebuild the code-import subgraph for `scope` from `root` (a Python
        source tree) — the CB2 first-slice capability. A full rebuild (not
        the incremental `write()`) is correct here: the extractor
        re-derives the WHOLE import graph from source every time, so there
        is nothing hand-asserted to preserve across a rebuild — unlike a
        general `write()` caller who must never have unrelated data wiped.
        Returns a summary in `notes`; `nodes`/`edges` stay empty (the real
        signal is the read methods afterward)."""
        if not scope.user_id:
            return GraphResult(degraded=True, notes="missing user_id — refused, fail-closed")
        if not root.is_dir():
            # replace_code_graph is a full wipe-then-rebuild: a typo'd or
            # since-removed root would otherwise silently empty this scope's
            # ENTIRE existing graph rather than error — refuse instead.
            return GraphResult(degraded=True, notes=f"root path does not exist: {root}")
        graph = await asyncio.to_thread(build_code_import_graph, root)
        ok = await asyncio.to_thread(graph_store.replace_code_graph, scope, graph)
        if not ok:
            return GraphResult(degraded=True, notes="graph store unavailable")
        return GraphResult(notes=f"built {len(graph.nodes)} files, {len(graph.edges)} import edges")

    async def delete_user(self, user_id: str) -> None:
        """Right-to-erasure: purge every graph-tier node for this user
        (CodeFile + Mission/Task). Not part of GraphPort — a delivery-layer
        surface, same shape as `MemoryManager.delete_user`, which calls this
        so an account deletion actually clears the graph tier instead of
        silently leaving it populated."""
        if not user_id:
            return
        await asyncio.to_thread(graph_store.delete_user, user_id)
        await asyncio.to_thread(mission_graph_store.delete_user, user_id)


# Process-level singleton; wiring hands this to the orchestrator's ports.
manager = GraphManager()
