"""
core/memory/graph_store.py

Kuzu access — the ONLY module that opens the Kuzu database or constructs a
Cypher query. Mirrors `store.py`'s discipline for the vector tiers: every
query carries a mandatory scope baked into the node id and re-checked in the
WHERE clause, and a call without a `user_id` is refused before it touches the
database (fail-closed — §V.20 carries over to the graph per the ratified
GraphPort design, `proposals/archive/to-backend/2026-07-05_graph-port-design.md`).

Kuzu is embedded (on-disk, single process, no server) — there is no remote
client to be "down"; the only fault modes are the db path being
unwritable/corrupt or the import failing. Both degrade the way `store.py`
degrades a dead Qdrant: log + return an empty, `degraded=True` result, never
raise into a caller. Writes here are batch/offline (one full graph rebuild
per call, not a per-turn write), so there is no concurrent-writer contention
to manage — Kuzu's single-writer embedded model is a non-issue at this scale.

`GraphManager` is the sole caller of this module and the sole implementer of
the port (`core/memory/graph_manager.py`); nothing above `core/memory/`
should ever import this file directly.

`GraphScope` is imported straight from `foundation` (the same shared type the
port uses) — no duplicate here. Everything else stays internal:
`GraphReadResult` is the bare-path read shape `graph_manager.py` adapts into
the port's `GraphResult`/`GraphNode` objects, the same layering `store.py`
has relative to `MemoryItem`/`HydrationPackage` in `manager.py`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from foundation import GraphScope, get_root

from .config import GRAPH_DISABLED as DISABLED
from .config import graph_db_path_override
from .graph_extract import CodeImportGraph

log = logging.getLogger(__name__)

# breaks_if_removed's hop bound — a cyclic/dense graph can't hang the door,
# same spirit as ORCHESTRATOR_MAX_TURNS bounding the orchestrator's loop.
MAX_HOPS_CEILING = 20

_db = None
_conn = None
_schema_ready = False


@dataclass(slots=True)
class GraphReadResult:
    """Internal read shape — graph_manager.py adapts this to the port's
    GraphResult once the contract lands. degraded=True means the graph was
    wanted but unavailable (missing scope, or Kuzu down) — distinct from a
    healthy empty result (scope valid, store up, genuinely no edges)."""
    paths: frozenset[str] = field(default_factory=frozenset)
    degraded: bool = False
    notes: str = ""


def _db_path() -> str:
    env = graph_db_path_override()
    if env:
        return env
    path = get_root() / "core" / "memory" / "data" / "graph_db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def _clear_empty_directory_in_kuzus_way(path: str) -> None:
    """Kuzu manages its db path itself and refuses to open ANY pre-existing
    directory there — even a freshly-created empty one (verified against
    real Kuzu 0.11.3: 'Database path cannot be a directory'). An ops script
    doing a blanket `mkdir -p` over every expected data path is a plausible,
    entirely reasonable deploy convention that would otherwise make the
    graph store fail closed forever with no recovery. An EMPTY directory
    can't be a real database, so clear it out of Kuzu's way; a NON-empty one
    is left completely alone — never guess at deleting something that might
    be real data."""
    p = Path(path)
    if p.is_dir() and not any(p.iterdir()):
        p.rmdir()


def _kuzu():
    """Lazy db + connection. Returns None while disabled/unavailable."""
    global _db, _conn
    if DISABLED:
        return None
    if _conn is None:
        try:
            import kuzu

            path = _db_path()
            _clear_empty_directory_in_kuzus_way(path)
            _db = kuzu.Database(path)
            _conn = kuzu.Connection(_db)
            _ensure_schema(_conn)
        except Exception as exc:
            log.warning("kuzu unavailable: %s", exc)
            _db = None
            _conn = None
            return None
    return _conn


def is_down() -> bool:
    """True while the graph store is disabled/unreachable — lets the manager
    tell 'no edges found' apart from 'graph unavailable'."""
    return DISABLED or _kuzu() is None


def healthcheck() -> bool:
    """Open the db now (lazy init) so the first real call doesn't pay the
    connect cost. Best-effort, mirrors store.py's healthcheck()."""
    return _kuzu() is not None


def _already_exists(exc: Exception) -> bool:
    return "already exists" in str(exc).lower()


def _ensure_schema(conn: Any) -> None:
    global _schema_ready
    if _schema_ready:
        return
    try:
        conn.execute(
            "CREATE NODE TABLE CodeFile("
            "id STRING, user_id STRING, repo_id STRING, path STRING, "
            "PRIMARY KEY(id))"
        )
    except RuntimeError as exc:
        if not _already_exists(exc):
            raise
    try:
        conn.execute("CREATE REL TABLE IMPORTS(FROM CodeFile TO CodeFile, origin STRING)")
    except RuntimeError as exc:
        if not _already_exists(exc):
            raise
    _schema_ready = True


def node_id(scope: GraphScope, path: str) -> str:
    """Public (not `_`-private): `graph_manager.py` mints/parses the same id
    scheme when translating the port's opaque `node_id` <-> this module's
    bare `path` — single source of truth for the format, no drift risk."""
    return f"{scope.user_id}|{scope.repo_id}|{path}"


def _clamp_hops(max_hops: object) -> int:
    """Clamp to [1, MAX_HOPS_CEILING]. Never raises: a malformed max_hops
    (e.g. a future tool-calling caller passing a model-supplied argument
    that isn't a clean int) falls back to 1 rather than propagating a
    ValueError/TypeError out of a read path this module promises never
    raises."""
    try:
        return max(1, min(int(max_hops), MAX_HOPS_CEILING))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1


def replace_code_graph(scope: GraphScope, graph: CodeImportGraph) -> bool:
    """Batch-replace the entire CodeFile/IMPORTS subgraph for `scope` with
    `graph`. Full replace, not incremental merge — appropriate for a batch
    build (the extractor re-walks the whole tree each time), and it means a
    file removed from the repo also disappears from the graph. Returns False
    (leaving any prior data untouched) on an invalid scope or a down store —
    never raises, never partially commits."""
    if not scope.user_id:
        log.warning("graph write refused: missing user_id (fail-closed)")
        return False
    conn = _kuzu()
    if conn is None:
        return False
    try:
        conn.execute(
            "MATCH (f:CodeFile) WHERE f.user_id=$user_id AND f.repo_id=$repo_id DETACH DELETE f",
            {"user_id": scope.user_id, "repo_id": scope.repo_id},
        )
        rows = [
            {
                "id": node_id(scope, path),
                "user_id": scope.user_id,
                "repo_id": scope.repo_id,
                "path": path,
            }
            for path in graph.nodes
        ]
        if rows:
            conn.execute(
                "UNWIND $rows AS r CREATE (f:CodeFile "
                "{id: r.id, user_id: r.user_id, repo_id: r.repo_id, path: r.path})",
                {"rows": rows},
            )
        edges = [
            {"src": node_id(scope, src), "dst": node_id(scope, dst), "origin": "inferred"}
            for src, dst in graph.edges
        ]
        if edges:
            conn.execute(
                "UNWIND $edges AS e "
                "MATCH (s:CodeFile {id: e.src}), (d:CodeFile {id: e.dst}) "
                "CREATE (s)-[:IMPORTS {origin: e.origin}]->(d)",
                {"edges": edges},
            )
        return True
    except Exception as exc:
        log.warning("kuzu write failed (graph state may be partial for this scope): %s", exc)
        return False


def depends_on(scope: GraphScope, path: str, *, max_hops: int = 1) -> GraphReadResult:
    """Files `path` imports, up to max_hops. Outgoing traversal."""
    return _traverse(scope, path, max_hops, forward=True)


def dependents_of(scope: GraphScope, path: str, *, max_hops: int = 1) -> GraphReadResult:
    """Files that import `path`, up to max_hops. Incoming traversal — the
    inverse of depends_on."""
    return _traverse(scope, path, max_hops, forward=False)


def breaks_if_removed(scope: GraphScope, path: str) -> GraphReadResult:
    """Transitive closure of dependents_of, at the hop ceiling — every file
    whose import chain would break if `path` disappeared."""
    return dependents_of(scope, path, max_hops=MAX_HOPS_CEILING)


def lookup_by_path(scope: GraphScope, path: str) -> GraphReadResult:
    """Existence check for one CodeFile node (no traversal) — the primitive
    behind `GraphPort.lookup(natural_key=...)`. `paths == {path}` if it
    exists in this scope, empty if not. Same fail-closed/degrade discipline
    as the traversal reads."""
    if not scope.user_id:
        return GraphReadResult(degraded=True, notes="missing user_id — refused, fail-closed")
    conn = _kuzu()
    if conn is None:
        return GraphReadResult(degraded=True, notes="graph store unavailable")
    try:
        result = conn.execute(
            "MATCH (f:CodeFile {id: $id, user_id: $user_id, repo_id: $repo_id}) RETURN f.path",
            {"id": node_id(scope, path), "user_id": scope.user_id, "repo_id": scope.repo_id},
        )
        paths = frozenset(row[0] for row in result.get_all())
        return GraphReadResult(paths=paths)
    except Exception as exc:
        log.warning("kuzu read failed (degrading): %s", exc)
        return GraphReadResult(degraded=True, notes="graph store unavailable")


def _traverse(scope: GraphScope, path: str, max_hops: int, *, forward: bool) -> GraphReadResult:
    if not scope.user_id:
        return GraphReadResult(degraded=True, notes="missing user_id — refused, fail-closed")
    conn = _kuzu()
    if conn is None:
        return GraphReadResult(degraded=True, notes="graph store unavailable")
    hops = _clamp_hops(max_hops)
    nid = node_id(scope, path)
    # Hop bound is an internally-clamped int (never user/model input) spliced
    # into the pattern — Kuzu's Cypher dialect does not accept a parameter
    # inside a variable-length relationship bound (`*1..$n` fails to parse).
    if forward:
        query = (
            f"MATCH (a:CodeFile {{id: $id}})-[:IMPORTS*1..{hops}]->(b:CodeFile) "
            "WHERE a.user_id = $user_id AND a.repo_id = $repo_id "
            "AND b.user_id = $user_id AND b.repo_id = $repo_id "
            "RETURN DISTINCT b.path"
        )
    else:
        query = (
            f"MATCH (a:CodeFile)-[:IMPORTS*1..{hops}]->(b:CodeFile {{id: $id}}) "
            "WHERE a.user_id = $user_id AND a.repo_id = $repo_id "
            "AND b.user_id = $user_id AND b.repo_id = $repo_id "
            "RETURN DISTINCT a.path"
        )
    try:
        result = conn.execute(
            query, {"id": nid, "user_id": scope.user_id, "repo_id": scope.repo_id}
        )
        paths = frozenset(row[0] for row in result.get_all())
        return GraphReadResult(paths=paths)
    except Exception as exc:
        log.warning("kuzu read failed (degrading): %s", exc)
        return GraphReadResult(degraded=True, notes="graph store unavailable")


def upsert_nodes(scope: GraphScope, rows: list[dict]) -> list[str]:
    """Incrementally MERGE each CodeFile node by id (idempotent — a repeat
    call just refreshes path/user_id/repo_id rather than duplicating).
    Distinct from `replace_code_graph`: this never deletes anything, so it is
    the primitive the general `GraphPort.write()` uses (an arbitrary caller
    adding one node must never wipe the rest of the scope's graph). Rows
    whose own user_id/repo_id don't match `scope` are silently dropped
    (defense in depth — `graph_manager.py` should already have filtered
    these). Returns the ids actually applied; empty on an invalid scope or a
    down store — never raises."""
    if not scope.user_id:
        log.warning("graph node upsert refused: missing user_id (fail-closed)")
        return []
    conn = _kuzu()
    if conn is None:
        return []
    accepted = [
        r for r in rows
        if r.get("user_id") == scope.user_id and r.get("repo_id", "") == scope.repo_id
    ]
    if not accepted:
        return []
    try:
        conn.execute(
            "UNWIND $rows AS r "
            "MERGE (f:CodeFile {id: r.id}) "
            "ON CREATE SET f.user_id = r.user_id, f.repo_id = r.repo_id, f.path = r.path "
            "ON MATCH SET f.path = r.path",
            {"rows": accepted},
        )
        return [r["id"] for r in accepted]
    except Exception as exc:
        log.warning("kuzu node upsert failed: %s", exc)
        return []


def upsert_edges(scope: GraphScope, rows: list[dict]) -> list[dict]:
    """Batch-upsert IMPORTS edges (each row: src/dst node ids + origin) for
    `scope`. MERGE is by connectivity only (never duplicates a parallel edge
    on a repeat call). An edge already stored with origin=ASSERTED is left
    untouched — asserted always wins (§5.2) — such a row is dropped, not
    applied. An edge naming an endpoint that isn't (yet) a CodeFile node in
    this scope silently fails to apply (Kuzu's MATCH finds nothing) rather
    than erroring — `write()` upserts nodes before edges in the same call, so
    this only bites a caller naming a node it never wrote. Also means an edge
    naming a foreign-scope node id can never bridge two tenants' graphs: the
    MATCH is scope-filtered on both endpoints. Returns the rows actually
    applied — same 'no phantom writes' discipline as
    `record_write_proposals`. Empty on an invalid scope or a down store."""
    if not scope.user_id:
        log.warning("graph edge upsert refused: missing user_id (fail-closed)")
        return []
    if not rows:
        return []
    conn = _kuzu()
    if conn is None:
        return []
    params = {"rows": rows, "uid": scope.user_id, "rid": scope.repo_id}
    try:
        protected = conn.execute(
            "UNWIND $rows AS e "
            "MATCH (s:CodeFile {id: e.src, user_id: $uid, repo_id: $rid})"
            "-[r:IMPORTS]->"
            "(d:CodeFile {id: e.dst, user_id: $uid, repo_id: $rid}) "
            "WHERE r.origin = 'asserted' "
            "RETURN e.src, e.dst",
            params,
        )
        protected_pairs = {(r[0], r[1]) for r in protected.get_all()}
        candidates = [r for r in rows if (r["src"], r["dst"]) not in protected_pairs]
        if not candidates:
            return []
        candidate_params = {"rows": candidates, "uid": scope.user_id, "rid": scope.repo_id}
        conn.execute(
            "UNWIND $rows AS e "
            "MATCH (s:CodeFile {id: e.src, user_id: $uid, repo_id: $rid}), "
            "(d:CodeFile {id: e.dst, user_id: $uid, repo_id: $rid}) "
            "MERGE (s)-[r:IMPORTS]->(d) "
            "ON CREATE SET r.origin = e.origin "
            "ON MATCH SET r.origin = e.origin",
            candidate_params,
        )
        applied = conn.execute(
            "UNWIND $rows AS e "
            "MATCH (s:CodeFile {id: e.src, user_id: $uid, repo_id: $rid})"
            "-[r:IMPORTS]->"
            "(d:CodeFile {id: e.dst, user_id: $uid, repo_id: $rid}) "
            "RETURN e.src, e.dst",
            candidate_params,
        )
        applied_pairs = {(r[0], r[1]) for r in applied.get_all()}
        return [r for r in candidates if (r["src"], r["dst"]) in applied_pairs]
    except Exception as exc:
        log.warning("kuzu edge upsert failed: %s", exc)
        return []
