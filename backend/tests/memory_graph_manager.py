"""
`GraphManager` — behavioural proof that the sole `foundation.GraphPort`
implementer (`core/memory/graph_manager.py`) is real, not a stub: it
satisfies the Protocol, correctly adapts `graph_store`'s bare-path shapes to
the port's public `GraphNode`/`GraphEdge`/`GraphResult`, and every promise the
placed contract makes actually holds THROUGH THE PORT (not just in the
internal `graph_store` primitives already covered by `memory_graph_store.py`).

Every test runs against a REAL embedded Kuzu db (fresh tmp_path per test —
the `_fresh_graph_store` autouse fixture lives in `tests/conftest.py`, shared
with `memory_graph_store.py` rather than duplicated), no mocks for the happy
paths. Async `GraphPort` methods are driven via `asyncio.run()` inside plain
`def` tests (this codebase's convention — see `memory_store_fault.py`/
`memory_typed_knowledge.py` — no pytest-asyncio/anyio test plugin is wired
in, so a bare `async def test_...` silently fails to run at all).

  ✓ GraphManager satisfies `foundation.GraphPort` (isinstance, runtime_checkable)
  ✓ END-TO-END CB2 slice: build_code_graph over the REAL backend/ tree, then
    depends_on / breaks_if_removed answer correctly through the port
  ✓ fail-closed on missing scope — every one of the 5 port methods
  ✓ degrade-never-fail when Kuzu is down — every one of the 5 port methods
  ✓ write() accepts CODE_FILE/IMPORTS and honestly rejects any other
    label/scope mismatch (reported in notes, not silently dropped)
  ✓ asserted-immutability holds THROUGH write(), not just graph_store
  ✓ a node_id from another scope, or a garbage node_id, returns an empty
    (not degraded) result — no tenant-existence oracle
  ✓ lookup() by natural_key, by an unbuilt label, and by vector_id (inert
    until the fusion phase)
  ✓ build_code_graph refuses a nonexistent root instead of silently wiping
    the scope's existing graph via replace_code_graph's full-rebuild

Run:
    cd backend && .venv/bin/python -m pytest tests/memory_graph_manager.py -v
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import core.memory.graph_store as graph_store
from core.memory.graph_manager import GraphManager
from foundation import (
    EdgeLabel,
    EdgeOrigin,
    GraphEdge,
    GraphNode,
    GraphPort,
    GraphScope,
    NodeLabel,
)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def manager() -> GraphManager:
    return GraphManager()


def _code_file(scope: GraphScope, path: str) -> GraphNode:
    return GraphNode(
        node_id=graph_store.node_id(scope, path),
        label=NodeLabel.CODE_FILE,
        scope=scope,
        properties={"path": path},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Protocol conformance
# ─────────────────────────────────────────────────────────────────────────────

def test_graph_manager_satisfies_graphport_protocol(manager):
    assert isinstance(manager, GraphPort)


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end CB2 slice — the real backend/ tree, through the port
# ─────────────────────────────────────────────────────────────────────────────

def test_build_code_graph_over_real_backend_then_depends_on_through_port(manager):
    async def go():
        scope = GraphScope(user_id="system", repo_id="clannon-self")

        build_result = await manager.build_code_graph(scope, _BACKEND_ROOT)
        assert build_result.degraded is False
        assert "files" in build_result.notes

        manager_node = graph_store.node_id(scope, "core/memory/manager.py")
        store_node = graph_store.node_id(scope, "core/memory/store.py")

        deps = await manager.depends_on(scope, manager_node)
        assert any(n.node_id == store_node for n in deps.nodes)

        breaks = await manager.breaks_if_removed(scope, store_node)
        assert any(n.node_id == manager_node for n in breaks.nodes)
        # The read methods return real GraphNode objects, not bare strings.
        hit = next(n for n in breaks.nodes if n.node_id == manager_node)
        assert hit.label == NodeLabel.CODE_FILE
        assert hit.properties["path"] == "core/memory/manager.py"
        assert hit.scope == scope

    asyncio.run(go())


def test_dependents_of_is_the_inverse_through_the_port(manager, tmp_path):
    async def go():
        scope = GraphScope(user_id="u1")
        src_root = tmp_path / "src"
        src_root.mkdir()
        (src_root / "a.py").write_text("VALUE = 1\n")
        (src_root / "b.py").write_text("import a\n")

        await manager.build_code_graph(scope, src_root)
        a_id = graph_store.node_id(scope, "a.py")
        b_id = graph_store.node_id(scope, "b.py")

        dependents = await manager.dependents_of(scope, a_id)
        assert {n.node_id for n in dependents.nodes} == {b_id}

    asyncio.run(go())


def test_build_code_graph_refuses_a_nonexistent_root_instead_of_wiping(manager, tmp_path):
    async def go():
        scope = GraphScope(user_id="u1")
        real_root = tmp_path / "src"
        real_root.mkdir()
        (real_root / "a.py").write_text("VALUE = 1\n")
        (real_root / "b.py").write_text("import a\n")
        await manager.build_code_graph(scope, real_root)
        b_id = graph_store.node_id(scope, "b.py")
        assert (await manager.lookup(scope, natural_key="b.py")).nodes  # sanity: it's there

        # A typo'd/removed root must refuse, not silently wipe the existing
        # graph via replace_code_graph's full-rebuild-with-nothing.
        result = await manager.build_code_graph(scope, tmp_path / "does-not-exist")

        assert result.degraded is True
        assert "does not exist" in result.notes
        # The real graph built moments ago must still be intact.
        assert (await manager.lookup(scope, natural_key="b.py")).nodes
        assert {n.node_id for n in (await manager.dependents_of(scope, graph_store.node_id(scope, "a.py"))).nodes} == {b_id}

    asyncio.run(go())


# ─────────────────────────────────────────────────────────────────────────────
# Fail-closed on missing scope — all 5 port methods
# ─────────────────────────────────────────────────────────────────────────────

def test_all_read_methods_fail_closed_on_missing_user_id(manager):
    async def go():
        scope = GraphScope(user_id="")

        for result in (
            await manager.depends_on(scope, "anything"),
            await manager.dependents_of(scope, "anything"),
            await manager.breaks_if_removed(scope, "anything"),
            await manager.lookup(scope, natural_key="anything"),
        ):
            assert result.degraded is True
            assert result.nodes == []

    asyncio.run(go())


def test_write_fails_closed_on_missing_user_id(manager):
    async def go():
        scope = GraphScope(user_id="")

        result = await manager.write(scope, [], [])

        assert result.degraded is True

    asyncio.run(go())


# ─────────────────────────────────────────────────────────────────────────────
# Degrade-never-fail when Kuzu is down
# ─────────────────────────────────────────────────────────────────────────────

def test_all_methods_degrade_when_kuzu_disabled(manager, monkeypatch):
    async def go():
        monkeypatch.setattr(graph_store, "DISABLED", True)
        scope = GraphScope(user_id="u1")
        node = _code_file(scope, "a.py")

        assert (await manager.depends_on(scope, "x")).degraded is True
        assert (await manager.dependents_of(scope, "x")).degraded is True
        assert (await manager.breaks_if_removed(scope, "x")).degraded is True
        assert (await manager.lookup(scope, natural_key="x")).degraded is True
        assert (await manager.write(scope, [node], [])).degraded is True

    asyncio.run(go())


# ─────────────────────────────────────────────────────────────────────────────
# write() — honest accept/reject through the port
# ─────────────────────────────────────────────────────────────────────────────

def test_write_upserts_nodes_and_edges_then_queryable_via_depends_on(manager):
    async def go():
        scope = GraphScope(user_id="u1", repo_id="r1")
        a, b = _code_file(scope, "a.py"), _code_file(scope, "b.py")
        edge = GraphEdge(src_id=b.node_id, dst_id=a.node_id, label=EdgeLabel.IMPORTS)

        result = await manager.write(scope, [a, b], [edge])

        assert {n.node_id for n in result.nodes} == {a.node_id, b.node_id}
        assert result.edges == [edge]
        deps = await manager.depends_on(scope, b.node_id)
        assert {n.node_id for n in deps.nodes} == {a.node_id}

    asyncio.run(go())


def test_write_rejects_unsupported_node_label_with_an_honest_note(manager):
    async def go():
        scope = GraphScope(user_id="u1")
        entity = GraphNode(
            node_id="whatever", label=NodeLabel.ENTITY, scope=scope, properties={}
        )

        result = await manager.write(scope, [entity], [])

        assert result.nodes == []
        assert "entity" in result.notes
        assert "not yet backed" in result.notes

    asyncio.run(go())


def test_write_rejects_unsupported_edge_label_with_an_honest_note(manager):
    async def go():
        scope = GraphScope(user_id="u1")
        a, b = _code_file(scope, "a.py"), _code_file(scope, "b.py")
        await manager.write(scope, [a, b], [])
        bad_edge = GraphEdge(src_id=b.node_id, dst_id=a.node_id, label=EdgeLabel.RELATES_TO)

        result = await manager.write(scope, [], [bad_edge])

        assert result.edges == []
        assert "relates_to" in result.notes

    asyncio.run(go())


def test_write_rejects_node_whose_embedded_scope_mismatches_the_call(manager):
    async def go():
        scope = GraphScope(user_id="u1")
        foreign_scope = GraphScope(user_id="someone-else")
        node = GraphNode(
            node_id="x", label=NodeLabel.CODE_FILE, scope=foreign_scope, properties={"path": "x.py"}
        )

        result = await manager.write(scope, [node], [])

        assert result.nodes == []
        assert "did not match" in result.notes

    asyncio.run(go())


def test_write_rejects_edge_naming_a_foreign_scope_endpoint(manager):
    async def go():
        scope = GraphScope(user_id="u1")
        other_scope = GraphScope(user_id="bob")
        a = _code_file(scope, "a.py")
        await manager.write(scope, [a], [])
        foreign_edge = GraphEdge(
            src_id=graph_store.node_id(other_scope, "b.py"), dst_id=a.node_id, label=EdgeLabel.IMPORTS
        )

        result = await manager.write(scope, [], [foreign_edge])

        assert result.edges == []
        assert "outside this scope" in result.notes

    asyncio.run(go())


def test_asserted_edge_is_immutable_through_the_port(manager):
    async def go():
        scope = GraphScope(user_id="u1")
        a, b = _code_file(scope, "a.py"), _code_file(scope, "b.py")
        await manager.write(scope, [a, b], [])
        asserted = GraphEdge(
            src_id=b.node_id, dst_id=a.node_id, label=EdgeLabel.IMPORTS, origin=EdgeOrigin.ASSERTED
        )
        await manager.write(scope, [], [asserted])

        inferred_overwrite = GraphEdge(
            src_id=b.node_id, dst_id=a.node_id, label=EdgeLabel.IMPORTS, origin=EdgeOrigin.INFERRED
        )
        result = await manager.write(scope, [], [inferred_overwrite])

        # The port-level write() must report the overwrite attempt as NOT
        # applied — asserted always wins (§5.2) — mirroring the graph_store-
        # level guarantee already proven in memory_graph_store.py, but now
        # verified through the full public door.
        assert result.edges == []

    asyncio.run(go())


# ─────────────────────────────────────────────────────────────────────────────
# No tenant-existence oracle
# ─────────────────────────────────────────────────────────────────────────────

def test_garbage_node_id_returns_empty_not_degraded(manager):
    async def go():
        scope = GraphScope(user_id="u1")

        result = await manager.depends_on(scope, "not-a-real-id")

        assert result.degraded is False
        assert result.nodes == []

    asyncio.run(go())


def test_node_id_from_another_scope_returns_empty_not_a_leak(manager):
    async def go():
        scope_a = GraphScope(user_id="alice")
        scope_b = GraphScope(user_id="bob")
        a, b = _code_file(scope_b, "a.py"), _code_file(scope_b, "b.py")
        edge = GraphEdge(src_id=b.node_id, dst_id=a.node_id, label=EdgeLabel.IMPORTS)
        await manager.write(scope_b, [a, b], [edge])

        # Alice asking about Bob's real node_id must see nothing — not an
        # error, not a hint that it exists elsewhere.
        result = await manager.depends_on(scope_a, b.node_id)

        assert result.degraded is False
        assert result.nodes == []

    asyncio.run(go())


# ─────────────────────────────────────────────────────────────────────────────
# lookup()
# ─────────────────────────────────────────────────────────────────────────────

def test_lookup_by_natural_key_finds_the_node(manager):
    async def go():
        scope = GraphScope(user_id="u1")
        a = _code_file(scope, "a.py")
        await manager.write(scope, [a], [])

        result = await manager.lookup(scope, natural_key="a.py")

        assert [n.node_id for n in result.nodes] == [a.node_id]

    asyncio.run(go())


def test_lookup_by_unbuilt_label_is_empty_not_degraded(manager):
    async def go():
        scope = GraphScope(user_id="u1")

        result = await manager.lookup(scope, label=NodeLabel.ENTITY, natural_key="whatever")

        assert result.degraded is False
        assert result.nodes == []

    asyncio.run(go())


def test_lookup_by_vector_id_is_inert_until_fusion_phase(manager):
    async def go():
        scope = GraphScope(user_id="u1")

        result = await manager.lookup(scope, vector_id="some-qdrant-point-id")

        assert result.degraded is False
        assert result.nodes == []
        assert "fusion" in result.notes

    asyncio.run(go())
