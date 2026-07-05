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

`GraphManager` (not yet built — waiting on the foundation `GraphPort` contract)
is the sole caller of this module and the sole implementer of the port;
nothing above `core/memory/` should ever import this file directly.

This module is intentionally independent of `foundation/contracts/graph.py`:
the contract isn't placed yet, and this file's own `GraphScope`/`GraphReadResult`
are the internal shapes `graph_manager.py` will adapt to the port's public
dataclasses once it exists — the same layering `store.py` has relative to
`MemoryItem`/`HydrationPackage` in `manager.py`.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from foundation import get_root

from .graph_extract import CodeImportGraph

log = logging.getLogger(__name__)

_DB_PATH_ENV = "VRAKSHA_GRAPH_DB_PATH"
DISABLED = os.getenv("VRAKSHA_GRAPH_DISABLED", "0") == "1"

# breaks_if_removed's hop bound — a cyclic/dense graph can't hang the door,
# same spirit as ORCHESTRATOR_MAX_TURNS bounding the orchestrator's loop.
MAX_HOPS_CEILING = 20

_db = None
_conn = None
_schema_ready = False


@dataclass(frozen=True, slots=True)
class GraphScope:
    """user_id is ALWAYS primary, mandatory, fail-closed (§V.20). repo_id is
    an OPTIONAL sub-filter AND-ed under it — "" means the user's
    default/only repo, so user_id-only is a strict subset of this scope.
    Both ids must come from trusted ctx, never model output — the same rule
    as HydrationRequest.user_id."""
    user_id: str
    repo_id: str = ""

    @property
    def valid(self) -> bool:
        return bool(self.user_id)


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
    env = os.getenv(_DB_PATH_ENV)
    if env:
        return env
    path = get_root() / "core" / "memory" / "data" / "graph_db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def _kuzu():
    """Lazy db + connection. Returns None while disabled/unavailable."""
    global _db, _conn
    if DISABLED:
        return None
    if _conn is None:
        try:
            import kuzu

            _db = kuzu.Database(_db_path())
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


def _node_id(scope: GraphScope, path: str) -> str:
    return f"{scope.user_id}|{scope.repo_id}|{path}"


def _clamp_hops(max_hops: int) -> int:
    return max(1, min(int(max_hops), MAX_HOPS_CEILING))


def replace_code_graph(scope: GraphScope, graph: CodeImportGraph) -> bool:
    """Batch-replace the entire CodeFile/IMPORTS subgraph for `scope` with
    `graph`. Full replace, not incremental merge — appropriate for a batch
    build (the extractor re-walks the whole tree each time), and it means a
    file removed from the repo also disappears from the graph. Returns False
    (leaving any prior data untouched) on an invalid scope or a down store —
    never raises, never partially commits."""
    if not scope.valid:
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
                "id": _node_id(scope, path),
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
            {"src": _node_id(scope, src), "dst": _node_id(scope, dst), "origin": "inferred"}
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


def _traverse(scope: GraphScope, path: str, max_hops: int, *, forward: bool) -> GraphReadResult:
    if not scope.valid:
        return GraphReadResult(degraded=True, notes="missing user_id — refused, fail-closed")
    conn = _kuzu()
    if conn is None:
        return GraphReadResult(degraded=True, notes="graph store unavailable")
    hops = _clamp_hops(max_hops)
    node_id = _node_id(scope, path)
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
            query, {"id": node_id, "user_id": scope.user_id, "repo_id": scope.repo_id}
        )
        paths = frozenset(row[0] for row in result.get_all())
        return GraphReadResult(paths=paths)
    except Exception as exc:
        log.warning("kuzu read failed (degrading): %s", exc)
        return GraphReadResult(degraded=True, notes="graph store unavailable")
