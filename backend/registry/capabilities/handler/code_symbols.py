"""
CB2 code-symbol tier — server-side, automatic, never model-facing (`ExpertHandler.
_index_code_symbols` calls `index_code_symbols` after an expert's own run finishes,
mirroring `_capture_artifacts`/`_snapshot_mission_workspace`; the model designates
nothing, unlike output artifacts). Writes every function/type definition in the
workspace as an `ENTITY` node (`entity_type`), `CALLS` edges between them, and a
`DERIVED_FROM` edge from each to the active mission. Ratified design:
proposals/archive/to-backend/2026-07-26_cb2-code-symbol-tier-design.md.

Reuses the def-type/declarator-unwrap grammar knowledge `tools/ast_search.py`
already solved (Python's plain `name` field; C's function name sitting behind a
declarator-wrapper chain) — re-derived here rather than imported, since `registry/`
importing FROM a specific `tools/` module would reverse the intended dependency
direction (tools self-register INTO registry, never the other way). Small and
stable grammar knowledge, not business logic at risk of drifting apart.

v1 scope, explicit not silent: a `CALLS` edge is written only when the callee's
plain name resolves to EXACTLY ONE definition among everything just scanned in
this pass — an ambiguous or unresolved call-site is silently not written (same
posture as `tools/dep_graph.py`'s unresolved imports, except there is no per-call
return value here to surface it on — the whole pass is automatic). No cross-run
persistence of the symbol index itself (each pass re-derives it fresh); a repeat
write on the same `(path, name)` MERGES in place (`GraphPort.write()`'s existing
node-mutation semantics), it does not duplicate.
"""

from __future__ import annotations

import tree_sitter_c as tsc
import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from foundation import EdgeLabel, EdgeOrigin, GraphEdge, GraphNode, GraphPort, GraphScope, NodeLabel, VrakshaContext

_EXT_LANGUAGE = {"py": "python", "c": "c", "h": "c"}
_PARSERS = {
    "python": Parser(Language(tspython.language())),
    "c": Parser(Language(tsc.language())),
}

_MAX_FILES_SCANNED = 500     # matches ast_search.py/dep_graph.py's own scan-cost bound
_MAX_FILE_BYTES = 2_000_000  # matches ast_search.py/dep_graph.py's own per-file bound
_MAX_SYMBOLS = 2_000         # bounds the graph-write payload for one pass


def _c_declarator_name(node: Node | None) -> Node | None:
    """Walk a C declarator chain (pointer/array/parenthesized/function) down to the
    plain identifier at its core — same shape as `tools/ast_search.py`'s helper of
    the same name, re-derived here (see module docstring)."""
    while node is not None and node.type != "identifier":
        node = node.child_by_field_name("declarator")
    return node


def _py_symbols(root: Node, path: str) -> tuple[list[tuple[str, str]], list[tuple[str | None, str]]]:
    """One Python file's (definitions, calls). `definitions` = `(name, entity_type)`.
    `calls` = `(caller_canonical_name_or_None, callee_plain_name)` — the caller is
    the INNERMOST enclosing `def` at the call-site (structurally exact, path-
    qualified already); `None` for a call at module top level, which has no
    function ENTITY to attribute it to and is dropped."""
    defs: list[tuple[str, str]] = []
    calls: list[tuple[str | None, str]] = []

    def walk(node: Node, enclosing: str | None) -> None:
        current = enclosing
        if node.type == "function_definition":
            n = node.child_by_field_name("name")
            if n is not None:
                name = n.text.decode()
                defs.append((name, "function"))
                current = f"{path}::{name}"
        elif node.type == "class_definition":
            n = node.child_by_field_name("name")
            if n is not None:
                defs.append((n.text.decode(), "class"))
        elif node.type == "call":
            fn = node.child_by_field_name("function")
            if fn is not None and fn.type == "identifier":
                calls.append((enclosing, fn.text.decode()))
        for child in node.children:
            walk(child, current)

    walk(root, None)
    return defs, calls


def _c_symbols(root: Node, path: str) -> tuple[list[tuple[str, str]], list[tuple[str | None, str]]]:
    """C file equivalent of `_py_symbols` — `struct`/`union`/`enum` specifiers are
    definitions too (never enclose a call, so they never become a `caller`)."""
    defs: list[tuple[str, str]] = []
    calls: list[tuple[str | None, str]] = []
    _NAMED_KINDS = {"struct_specifier": "struct", "union_specifier": "union", "enum_specifier": "enum"}

    def walk(node: Node, enclosing: str | None) -> None:
        current = enclosing
        if node.type == "function_definition":
            n = _c_declarator_name(node.child_by_field_name("declarator"))
            if n is not None:
                name = n.text.decode()
                defs.append((name, "function"))
                current = f"{path}::{name}"
        elif node.type in _NAMED_KINDS:
            n = node.child_by_field_name("name")
            if n is not None:
                defs.append((n.text.decode(), _NAMED_KINDS[node.type]))
        elif node.type == "call_expression":
            fn = node.child_by_field_name("function")
            if fn is not None and fn.type == "identifier":
                calls.append((enclosing, fn.text.decode()))
        for child in node.children:
            walk(child, current)

    walk(root, None)
    return defs, calls


_WALKERS = {"python": _py_symbols, "c": _c_symbols}


async def _mission_node_id(graph: GraphPort, scope: GraphScope, mission_id: str) -> str | None:
    """The active mission's real, port-assigned node id — read back the same way
    `mission_operate.py::read_mission_state` does (`members()`, filtered client-side
    on the `mission_id` property; `MISSION` node ids are never caller-supplied)."""
    result = await graph.members(scope, NodeLabel.MISSION)
    if result.degraded:
        return None
    return next((n.node_id for n in result.nodes if n.properties.get("mission_id") == mission_id), None)


async def index_code_symbols(graph: GraphPort, ctx: VrakshaContext, workspace) -> tuple[int, int, str]:
    """Scan `workspace`, write every definition as an `ENTITY` node + resolved
    `CALLS` edges + (if a mission is active) `DERIVED_FROM` edges to it, into
    `graph`. Returns `(entities_written, calls_edges_written, error)` — `error` is
    `""` on success, including the honest partial case of a missing mission node
    (ENTITY/CALLS still get written; only the DERIVED_FROM tagging is skipped)."""
    try:
        all_paths = await workspace.list()
    except Exception as exc:  # noqa: BLE001 — a listing fault means nothing to index this pass
        return 0, 0, str(exc)[:200]

    targets: list[tuple[str, str]] = []
    for p in all_paths:
        ext = p.rsplit(".", 1)[-1].lower() if "." in p else ""
        lang = _EXT_LANGUAGE.get(ext)
        if lang is not None:
            targets.append((p, lang))
    targets = targets[:_MAX_FILES_SCANNED]

    symbols: dict[str, str] = {}                       # canonical_name ("path::name") -> entity_type
    name_to_canonicals: dict[str, list[str]] = {}       # plain name -> every canonical_name defining it
    calls: list[tuple[str, str]] = []                   # (caller_canonical, callee_plain_name)

    for path, lang in targets:
        try:
            data = await workspace.read_bytes(path)
        except Exception:  # noqa: BLE001 — one unreadable file must not sink the whole pass
            continue
        if len(data) > _MAX_FILE_BYTES:
            continue
        tree = _PARSERS[lang].parse(data)
        defs, file_calls = _WALKERS[lang](tree.root_node, path)
        for name, kind in defs:
            canonical = f"{path}::{name}"
            symbols[canonical] = kind
            name_to_canonicals.setdefault(name, []).append(canonical)
        calls.extend((caller, callee) for caller, callee in file_calls if caller is not None)
        if len(symbols) >= _MAX_SYMBOLS:
            break

    if not symbols:
        return 0, 0, ""

    scope = GraphScope(user_id=ctx.user_id)
    nodes = [
        GraphNode(node_id="", label=NodeLabel.ENTITY, scope=scope,
                  properties={"canonical_name": canonical, "entity_type": kind})
        for canonical, kind in symbols.items()
    ]
    node_write = await graph.write(scope, nodes, [])
    if node_write.degraded:
        return 0, 0, node_write.notes or "graph degraded writing symbols"

    # node ids are never caller-supplied (mission_operate.py's own hard-won lesson) —
    # read the real, port-assigned ids back before building any edge that references them
    members_result = await graph.members(scope, NodeLabel.ENTITY)
    id_by_canonical = {
        n.properties.get("canonical_name"): n.node_id
        for n in members_result.nodes
        if n.properties.get("canonical_name") in symbols
    }

    edges: list[GraphEdge] = []
    for caller_canonical, callee_name in calls:
        resolved = name_to_canonicals.get(callee_name)
        if not resolved or len(resolved) != 1:
            continue   # ambiguous or unresolved -- v1 scope, see module docstring
        src_id = id_by_canonical.get(caller_canonical)
        dst_id = id_by_canonical.get(resolved[0])
        if src_id is not None and dst_id is not None:
            edges.append(GraphEdge(src_id=src_id, dst_id=dst_id, label=EdgeLabel.CALLS, origin=EdgeOrigin.INFERRED))

    if ctx.mission_id:
        mission_node_id = await _mission_node_id(graph, scope, ctx.mission_id)
        if mission_node_id is not None:
            edges.extend(
                GraphEdge(src_id=eid, dst_id=mission_node_id, label=EdgeLabel.DERIVED_FROM, origin=EdgeOrigin.INFERRED)
                for eid in id_by_canonical.values()
            )

    if not edges:
        return len(symbols), 0, ""
    edge_write = await graph.write(scope, [], edges)
    if edge_write.degraded:
        return len(symbols), 0, edge_write.notes or "graph degraded writing edges"
    calls_written = sum(1 for e in edge_write.edges if e.label == EdgeLabel.CALLS)
    return len(symbols), calls_written, ""
