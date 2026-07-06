"""
The Kuzu wrapper — behavioural proof that `core.memory.graph_store` enforces
the ratified GraphPort scoping model
(`proposals/archive/to-backend/2026-07-05_graph-port-design.md` §6,
ratified in `to-memory/2026-07-05_graph-design-ratified-build-slice.md`) and
degrades the way `store.py` degrades a dead Qdrant.

Unlike Qdrant, Kuzu is embedded — no server, no `qdrant not reachable` skip.
Every test below runs against a REAL Kuzu database in a fresh tmp_path, not a
mock, so a schema/query typo fails here. The `_fresh_graph_store` autouse
fixture lives in `tests/conftest.py` (shared with `memory_graph_manager.py`
rather than duplicated).

  ✓ a missing user_id is refused fail-closed (§V.20) — read AND write, before
    the database is even touched
  ✓ composite scope: repo_id is an AND-ed sub-filter UNDER user_id, never a
    scope on its own — same user_id, different repo_id, cannot see each
    other's files
  ✓ repo_id="" is the user's default/only repo — a strict subset, not a
    wildcard that also matches a named repo
  ✓ write -> read round-trip is correct: depends_on / dependents_of /
    breaks_if_removed on a real on-disk graph
  ✓ replace_code_graph is a FULL rebuild, not a merge — a file dropped from
    one build to the next actually disappears
  ✓ a hop request beyond MAX_HOPS_CEILING is clamped, not rejected/crashed
  ✓ Kuzu unavailable degrades cleanly (degraded=True, empty paths), never
    raises
  ✓ delete_user purges only the target user's CodeFile nodes (tenant
    isolation holds for erasure too), no-ops on a missing user_id, and
    degrades silently on a down store — the graph tier's half of
    right-to-erasure (previously missing entirely)
  ✓ upsert_nodes / upsert_edges (the incremental primitives graph_manager's
    GraphPort.write() uses) — idempotent (no duplicate parallel edges on a
    repeat call), an existing ASSERTED edge is immutable (§5.2, "asserted
    always wins" — a later inferred write never overwrites it), an edge
    naming a nonexistent endpoint silently fails to apply rather than
    erroring, and a row whose own scope fields don't match is dropped
  ✓ a malformed max_hops (not an int — a future tool-calling caller passing
    a model-supplied argument verbatim is a realistic source) degrades to a
    safe default instead of raising ValueError/TypeError out of a read path
    that promises it never raises
  ✓ a pre-existing EMPTY directory at the db path (e.g. an ops script's
    blanket `mkdir -p` over every expected data path) does not permanently
    wedge the store — Kuzu refuses to open a directory at all, even an
    empty one, so graph_store clears it out of the way first; a NON-empty
    directory is left completely untouched (never guess at deleting
    something that might be real data)
  ✓ concurrent cold-start callers (the batch layer's multiple concurrent
    readers) construct the underlying kuzu.Database exactly once, not once
    per caller — a real race found auditing for batch-layer readiness

Run:
    cd backend && .venv/bin/python -m pytest tests/memory_graph_store.py -v
"""
from __future__ import annotations

import asyncio
import threading
import time

import pytest

import core.memory.graph_store as graph_store
from core.memory.graph_extract import CodeImportGraph
from core.memory.graph_store import GraphScope


def _chain_graph() -> CodeImportGraph:
    """c.py -> b.py -> a.py (c depends on b, b depends on a)."""
    return CodeImportGraph(
        nodes=frozenset({"a.py", "b.py", "c.py"}),
        edges=frozenset({("b.py", "a.py"), ("c.py", "b.py")}),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Fail-closed scoping
# ─────────────────────────────────────────────────────────────────────────────

def test_missing_user_id_refuses_read_fail_closed():
    scope = GraphScope(user_id="")

    result = graph_store.depends_on(scope, "a.py")

    assert result.degraded is True
    assert result.paths == frozenset()


def test_missing_user_id_refuses_write_fail_closed(tmp_path):
    scope = GraphScope(user_id="")

    ok = graph_store.replace_code_graph(scope, _chain_graph())

    assert ok is False
    # Nothing was written — a read under a VALID scope sees no data.
    valid = GraphScope(user_id="someone")
    assert graph_store.depends_on(valid, "c.py").paths == frozenset()


# ─────────────────────────────────────────────────────────────────────────────
# Write -> read round trip
# ─────────────────────────────────────────────────────────────────────────────

def test_write_then_read_round_trip():
    scope = GraphScope(user_id="u1", repo_id="r1")
    assert graph_store.replace_code_graph(scope, _chain_graph()) is True

    assert graph_store.depends_on(scope, "c.py", max_hops=1).paths == frozenset({"b.py"})
    assert graph_store.depends_on(scope, "c.py", max_hops=2).paths == frozenset({"b.py", "a.py"})
    assert graph_store.dependents_of(scope, "a.py", max_hops=1).paths == frozenset({"b.py"})
    assert graph_store.dependents_of(scope, "a.py", max_hops=2).paths == frozenset({"b.py", "c.py"})
    assert graph_store.breaks_if_removed(scope, "a.py").paths == frozenset({"b.py", "c.py"})
    assert graph_store.breaks_if_removed(scope, "c.py").paths == frozenset()


def test_hop_request_beyond_ceiling_is_clamped_not_rejected():
    scope = GraphScope(user_id="u1")
    graph_store.replace_code_graph(scope, _chain_graph())

    # Absurdly large max_hops must not crash or hang — it's clamped to
    # MAX_HOPS_CEILING internally, and the 2-hop chain still resolves fully.
    result = graph_store.depends_on(scope, "c.py", max_hops=10_000)

    assert result.degraded is False
    assert result.paths == frozenset({"b.py", "a.py"})


@pytest.mark.parametrize("bad_hops", ["not-a-number", None, [], float("nan")])
def test_malformed_max_hops_degrades_to_a_safe_default_not_a_crash(bad_hops):
    scope = GraphScope(user_id="u1")
    graph_store.replace_code_graph(scope, _chain_graph())

    # A future tool-calling consumer might pass max_hops straight from a
    # model's tool-call arguments — this must never raise into the caller,
    # same discipline as every other fault in this module.
    result = graph_store.depends_on(scope, "c.py", max_hops=bad_hops)

    assert result.degraded is False
    assert result.paths == frozenset({"b.py"})  # falls back to max_hops=1


def test_replace_is_a_full_rebuild_not_a_merge():
    scope = GraphScope(user_id="u1")
    graph_store.replace_code_graph(scope, _chain_graph())

    # b.py is removed from the tree entirely on the next build.
    smaller = CodeImportGraph(
        nodes=frozenset({"a.py", "c.py"}),
        edges=frozenset(),
    )
    graph_store.replace_code_graph(scope, smaller)

    assert graph_store.dependents_of(scope, "a.py", max_hops=5).paths == frozenset()


# ─────────────────────────────────────────────────────────────────────────────
# Composite (user_id, repo_id) scoping
# ─────────────────────────────────────────────────────────────────────────────

def test_repo_id_is_an_and_ed_subfilter_not_a_standalone_scope():
    same_user_repo_a = GraphScope(user_id="u1", repo_id="alpha")
    same_user_repo_b = GraphScope(user_id="u1", repo_id="beta")
    graph_store.replace_code_graph(same_user_repo_a, _chain_graph())

    # Same user_id, different repo_id — must NOT see alpha's graph.
    assert graph_store.depends_on(same_user_repo_b, "c.py").paths == frozenset()
    # The original scope is unaffected.
    assert graph_store.depends_on(same_user_repo_a, "c.py").paths == frozenset({"b.py"})


def test_default_repo_id_is_a_distinct_scope_from_a_named_repo():
    default_repo = GraphScope(user_id="u1", repo_id="")
    named_repo = GraphScope(user_id="u1", repo_id="clannon-self")
    graph_store.replace_code_graph(named_repo, _chain_graph())

    # repo_id="" is the user's default repo — a strict subset, not a
    # wildcard that also matches "clannon-self".
    assert graph_store.depends_on(default_repo, "c.py").paths == frozenset()
    assert graph_store.depends_on(named_repo, "c.py").paths == frozenset({"b.py"})


def test_different_users_never_see_each_others_graph_even_with_same_paths():
    user_a = GraphScope(user_id="alice")
    user_b = GraphScope(user_id="bob")
    graph_store.replace_code_graph(user_a, _chain_graph())
    graph_store.replace_code_graph(user_b, _chain_graph())

    # Both wrote identical file paths; each must only ever see their own.
    graph_store.replace_code_graph(
        user_a, CodeImportGraph(nodes=frozenset({"a.py"}), edges=frozenset())
    )
    assert graph_store.dependents_of(user_a, "a.py").paths == frozenset()
    assert graph_store.dependents_of(user_b, "a.py").paths == frozenset({"b.py"})


# ─────────────────────────────────────────────────────────────────────────────
# Degrade-never-fail
# ─────────────────────────────────────────────────────────────────────────────

def test_kuzu_disabled_degrades_read_and_write_cleanly(monkeypatch):
    monkeypatch.setattr(graph_store, "DISABLED", True)
    scope = GraphScope(user_id="u1")

    read = graph_store.depends_on(scope, "a.py")
    write_ok = graph_store.replace_code_graph(scope, _chain_graph())

    assert read.degraded is True
    assert write_ok is False


def test_kuzu_connection_failure_degrades_instead_of_raising(monkeypatch):
    scope = GraphScope(user_id="u1")
    graph_store.replace_code_graph(scope, _chain_graph())

    def _broken():
        return None

    monkeypatch.setattr(graph_store, "_kuzu", _broken)

    result = graph_store.depends_on(scope, "c.py")

    assert result.degraded is True
    assert result.paths == frozenset()


# ─────────────────────────────────────────────────────────────────────────────
# upsert_nodes / upsert_edges — the incremental primitives GraphPort.write() uses
# ─────────────────────────────────────────────────────────────────────────────

def _node_row(scope: GraphScope, path: str) -> dict:
    return {
        "id": graph_store.node_id(scope, path),
        "user_id": scope.user_id,
        "repo_id": scope.repo_id,
        "path": path,
    }


def test_upsert_nodes_then_edges_round_trips_through_depends_on():
    scope = GraphScope(user_id="u1", repo_id="r1")

    applied_nodes = graph_store.upsert_nodes(
        scope, [_node_row(scope, "a.py"), _node_row(scope, "b.py")]
    )
    assert set(applied_nodes) == {
        graph_store.node_id(scope, "a.py"), graph_store.node_id(scope, "b.py")
    }

    edge = {
        "src": graph_store.node_id(scope, "b.py"),
        "dst": graph_store.node_id(scope, "a.py"),
        "origin": "inferred",
    }
    applied_edges = graph_store.upsert_edges(scope, [edge])

    assert applied_edges == [edge]
    assert graph_store.depends_on(scope, "b.py").paths == frozenset({"a.py"})


def test_upsert_edges_is_idempotent_no_duplicate_parallel_edge():
    scope = GraphScope(user_id="u1")
    graph_store.upsert_nodes(scope, [_node_row(scope, "a.py"), _node_row(scope, "b.py")])
    edge = {
        "src": graph_store.node_id(scope, "b.py"),
        "dst": graph_store.node_id(scope, "a.py"),
        "origin": "inferred",
    }

    graph_store.upsert_edges(scope, [edge])
    graph_store.upsert_edges(scope, [edge])
    graph_store.upsert_edges(scope, [edge])

    # Still exactly one hop — a naive repeated CREATE would have produced 3
    # parallel edges; MERGE-by-connectivity must not duplicate.
    assert graph_store.depends_on(scope, "b.py").paths == frozenset({"a.py"})


def test_asserted_edge_is_immutable_to_a_later_inferred_upsert():
    scope = GraphScope(user_id="u1")
    graph_store.upsert_nodes(scope, [_node_row(scope, "a.py"), _node_row(scope, "b.py")])
    src, dst = graph_store.node_id(scope, "b.py"), graph_store.node_id(scope, "a.py")

    applied = graph_store.upsert_edges(scope, [{"src": src, "dst": dst, "origin": "asserted"}])
    assert applied  # the asserted write itself succeeds

    # A later INFERRED write attempting the same edge must be refused —
    # asserted always wins (§5.2) — and report nothing applied, not a
    # phantom success.
    rejected = graph_store.upsert_edges(scope, [{"src": src, "dst": dst, "origin": "inferred"}])
    assert rejected == []


def test_upsert_edge_with_missing_endpoint_silently_fails_to_apply():
    scope = GraphScope(user_id="u1")
    graph_store.upsert_nodes(scope, [_node_row(scope, "b.py")])
    ghost_edge = {
        "src": graph_store.node_id(scope, "b.py"),
        "dst": graph_store.node_id(scope, "ghost.py"),  # never upserted
        "origin": "inferred",
    }

    applied = graph_store.upsert_edges(scope, [ghost_edge])

    assert applied == []


def test_upsert_nodes_drops_rows_with_mismatched_scope_fields():
    scope = GraphScope(user_id="u1", repo_id="r1")
    foreign_row = {
        "id": "not-actually-scoped",
        "user_id": "someone-else",
        "repo_id": "",
        "path": "x.py",
    }

    applied = graph_store.upsert_nodes(scope, [foreign_row])

    assert applied == []


def test_upsert_nodes_and_edges_refuse_fail_closed_on_missing_user_id():
    scope = GraphScope(user_id="")

    assert graph_store.upsert_nodes(scope, [_node_row(scope, "a.py")]) == []
    assert graph_store.upsert_edges(scope, [{"src": "a", "dst": "b", "origin": "inferred"}]) == []


# ─────────────────────────────────────────────────────────────────────────────
# lookup_by_path — the primitive behind GraphPort.lookup()
# ─────────────────────────────────────────────────────────────────────────────

def test_lookup_by_path_finds_an_existing_node_and_misses_a_nonexistent_one():
    scope = GraphScope(user_id="u1")
    graph_store.upsert_nodes(scope, [_node_row(scope, "a.py")])

    assert graph_store.lookup_by_path(scope, "a.py").paths == frozenset({"a.py"})
    assert graph_store.lookup_by_path(scope, "nope.py").paths == frozenset()


def test_lookup_by_path_refuses_fail_closed_on_missing_user_id():
    result = graph_store.lookup_by_path(GraphScope(user_id=""), "a.py")

    assert result.degraded is True
    assert result.paths == frozenset()


# ─────────────────────────────────────────────────────────────────────────────
# Operational robustness — a pre-existing directory at the db path
# ─────────────────────────────────────────────────────────────────────────────

def test_pre_existing_empty_directory_at_db_path_does_not_wedge_the_store(tmp_path, monkeypatch):
    # Simulate an ops script's `mkdir -p` creating the path ahead of time —
    # NOT the fixture's usual "tmp_path/graph_db never existed" case.
    pre_created = tmp_path / "ops-precreated-graph-db"
    pre_created.mkdir()
    monkeypatch.setenv("VRAKSHA_GRAPH_DB_PATH", str(pre_created))
    graph_store._db = None
    graph_store._conn = None
    graph_store._schema_ready = False

    scope = GraphScope(user_id="u1")
    ok = graph_store.replace_code_graph(scope, _chain_graph())

    assert ok is True
    assert graph_store.depends_on(scope, "c.py").paths == frozenset({"b.py"})


def test_pre_existing_nonempty_directory_at_db_path_is_left_untouched(tmp_path, monkeypatch):
    pre_created = tmp_path / "ops-precreated-graph-db"
    pre_created.mkdir()
    sentinel = pre_created / "not-a-kuzu-file.txt"
    sentinel.write_text("do not delete me")
    monkeypatch.setenv("VRAKSHA_GRAPH_DB_PATH", str(pre_created))
    graph_store._db = None
    graph_store._conn = None
    graph_store._schema_ready = False

    result = graph_store.depends_on(GraphScope(user_id="u1"), "a.py")

    # Kuzu's own error still surfaces as a clean degrade — but the
    # unrelated file must never be silently deleted to "fix" it.
    assert result.degraded is True
    assert sentinel.exists()


# ─────────────────────────────────────────────────────────────────────────────
# Concurrency safety — the batch layer brings MULTIPLE concurrent readers to
# this substrate (Prime Directive audit, 2026-07-05); _kuzu()'s lazy init must
# not race.
# ─────────────────────────────────────────────────────────────────────────────

def test_concurrent_cold_start_constructs_kuzu_database_exactly_once(monkeypatch):
    """Widen _kuzu()'s check-then-act window (simulating real disk I/O latency)
    and prove _lock actually serializes it: N concurrent callers from a cold
    (uninitialized) state must open the underlying kuzu.Database exactly ONCE,
    not once per caller.

    Regression for a real race found auditing for the batch layer: without the
    lock, 10 concurrent callers each independently passed the `_conn is None`
    check and opened 10 separate Database handles on the same path — each
    individually survived (no crash), but 9 of the 10 handles leaked. That's
    exactly what concurrent batch readers hitting a cold process would multiply."""
    import kuzu as kuzu_module

    real_database = kuzu_module.Database
    construct_count = {"n": 0}
    count_lock = threading.Lock()

    class _SlowDatabase(real_database):
        def __init__(self, path, *a, **k):
            with count_lock:
                construct_count["n"] += 1
            time.sleep(0.05)  # widen the race window
            super().__init__(path, *a, **k)

    monkeypatch.setattr(kuzu_module, "Database", _SlowDatabase)

    async def go():
        return await asyncio.gather(
            *(asyncio.to_thread(graph_store._kuzu) for _ in range(10)),
            return_exceptions=True,
        )

    results = asyncio.run(go())
    assert not any(isinstance(r, BaseException) for r in results), (
        f"a concurrent cold start must never raise: {results}"
    )
    assert construct_count["n"] == 1, (
        f"kuzu.Database() must be constructed exactly once under a concurrent "
        f"cold start, got {construct_count['n']} — the lazy-init lock isn't "
        f"serializing callers"
    )


# ─────────────────────────────────────────────────────────────────────────────
# delete_user — the graph tier's right-to-erasure
# ─────────────────────────────────────────────────────────────────────────────

def test_delete_user_purges_only_the_target_users_code_files():
    owner, other = GraphScope(user_id="owner"), GraphScope(user_id="other")
    graph_store.replace_code_graph(owner, _chain_graph())
    graph_store.replace_code_graph(other, _chain_graph())

    graph_store.delete_user("owner")

    assert graph_store.depends_on(owner, "c.py").paths == frozenset()
    assert graph_store.lookup_by_path(owner, "a.py").paths == frozenset()
    # the other tenant's identical-looking graph is untouched
    assert graph_store.lookup_by_path(other, "a.py").paths == frozenset({"a.py"})


def test_delete_user_is_a_noop_on_missing_user_id():
    scope = GraphScope(user_id="owner")
    graph_store.replace_code_graph(scope, _chain_graph())

    graph_store.delete_user("")  # must not raise, must not touch anything

    assert graph_store.lookup_by_path(scope, "a.py").paths == frozenset({"a.py"})


def test_delete_user_degrades_silently_when_store_is_down(monkeypatch):
    monkeypatch.setattr(graph_store, "_kuzu", lambda: None)

    graph_store.delete_user("owner")  # must not raise
