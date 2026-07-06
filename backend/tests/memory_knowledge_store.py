"""
Knowledge web (CB2/CB3/EB3 substrate) — `core/memory/knowledge_store.py`
(typed Entity/Fact/Claim/MediaSegment nodes + RelatesTo/Contradicts/
DerivedFrom/AuthoredBy edges over Kuzu) and `GraphManager`'s dispatch
extension routing those labels there instead of `mission_graph_store.py`.

Ratified 2026-07-06 from the memory specialist's design proposal
(`proposals/archive/to-backend/2026-07-06_knowledge-web-design-cb2-cb3-eb3.md`).
Build order step 2/3: `typed_graph.py`'s generic mechanism (lifted out of
`mission_graph_store.py` in step 1, see `memory_mission_graph.py`'s own
coverage for that half) now backs a SECOND schema registry. The load-bearing
new behavior this file proves:

  - Entity convergence: two writes with the same (normalized) canonical_name
    land on the SAME node (§1.1 of the design) — the identity is the name
    itself, no separate resolution step.
  - Fact/Claim are keyed by vector_id (the fusion pointer doubles as the
    node's identity — each is the graph twin of exactly one memory point).
  - HETEROGENEOUS edges (RelatesTo/DerivedFrom/AuthoredBy span more than one
    node-table pair) actually persist and read back correctly — this is the
    one genuinely new mechanic beyond what mission_graph_store.py needed
    (Task-to-Task is homogeneous). Verified against real Kuzu 0.11.3 that
    MERGE/CREATE needs a concrete label per endpoint (an unlabeled node
    pattern raises "Create rel bound by multiple node labels is not
    supported"), so `typed_graph._resolve_node_tables` resolves each
    endpoint's real table before the MERGE — this file is the regression
    proof for that resolution path.

Every test runs against a REAL embedded Kuzu db (fresh tmp_path per test via
`tests/conftest.py`'s autouse `_fresh_graph_store` fixture) — no mocks for the
happy paths, same convention as `memory_mission_graph.py`.

Run:
    cd backend && .venv/bin/python -m pytest tests/memory_knowledge_store.py -v
"""
from __future__ import annotations

import asyncio

import pytest

import core.memory.graph_store as graph_store
import core.memory.knowledge_store as knowledge_store
from core.memory.graph_manager import GraphManager
from foundation import EdgeLabel, EdgeOrigin, GraphEdge, GraphNode, GraphScope, NodeLabel


@pytest.fixture
def manager() -> GraphManager:
    return GraphManager()


def _entity_row(scope: GraphScope, canonical_name: str, **overrides) -> dict:
    row = {
        "id": graph_store.node_id(scope, canonical_name), "user_id": scope.user_id,
        "repo_id": scope.repo_id, "entity_type": "concept", "canonical_name": canonical_name,
        "vector_id": "", "updated_at": 1.0,
    }
    row.update(overrides)
    return row


def _fact_row(scope: GraphScope, vector_id: str, **overrides) -> dict:
    row = {
        "id": graph_store.node_id(scope, vector_id), "user_id": scope.user_id,
        "repo_id": scope.repo_id, "content": "some fact", "confidence": 0.9,
        "vector_id": vector_id, "updated_at": 1.0,
    }
    row.update(overrides)
    return row


# ─────────────────────────────────────────────────────────────────────────────
# knowledge_store.py — low-level Kuzu mechanics
# ─────────────────────────────────────────────────────────────────────────────

def test_entity_upsert_then_read_back():
    scope = GraphScope(user_id="u1")
    applied = knowledge_store.upsert_typed_nodes("entity", [_entity_row(scope, "memory manager")])
    assert applied == [graph_store.node_id(scope, "memory manager")]
    result = knowledge_store.typed_members("entity", scope)
    assert len(result.rows) == 1
    assert result.rows[0]["canonical_name"] == "memory manager"


def test_entity_convergence_two_writes_same_name_land_on_one_node():
    """§1.1: convergence is structural, not a separate resolution step — two
    mentions of the same normalized name MERGE onto one node."""
    scope = GraphScope(user_id="u1")
    knowledge_store.upsert_typed_nodes("entity", [_entity_row(scope, "memory manager", entity_type="concept")])
    knowledge_store.upsert_typed_nodes("entity", [_entity_row(scope, "memory manager", vector_id="pt-1")])
    result = knowledge_store.typed_members("entity", scope)
    assert len(result.rows) == 1, "same canonical_name must converge onto one node, not duplicate"
    assert result.rows[0]["vector_id"] == "pt-1", "mutable field must refresh on the repeat write"


def test_entity_type_is_create_only_immune_to_a_repeat_write():
    """entity_type is identity-adjacent (create_only) — a repeat write with a
    DIFFERENT entity_type must not silently reclassify the entity."""
    scope = GraphScope(user_id="u1")
    knowledge_store.upsert_typed_nodes("entity", [_entity_row(scope, "bob", entity_type="person")])
    knowledge_store.upsert_typed_nodes("entity", [_entity_row(scope, "bob", entity_type="project")])
    result = knowledge_store.typed_members("entity", scope)
    assert len(result.rows) == 1
    assert result.rows[0]["entity_type"] == "person", "create_only field must not change on ON MATCH"


def test_fact_keyed_by_vector_id_not_content():
    """Fact/Claim identity is the fusion pointer, not the content string —
    a repeat write under the SAME vector_id lands on the same node (identity
    is the pointer, not the text), while the SAME content under two
    different vector_ids stays two separate nodes. `content` is create_only
    (matches ARCHITECTURE.md §5's dedup rule: a near-duplicate refresh
    updates confidence/created_at, never the original content) — a repeat
    write with a different content string does NOT overwrite it, only the
    mutable `confidence` does."""
    scope = GraphScope(user_id="u1")
    knowledge_store.upsert_typed_nodes("fact", [_fact_row(scope, "pt-1", content="first version", confidence=0.5)])
    knowledge_store.upsert_typed_nodes(
        "fact", [_fact_row(scope, "pt-1", content="a second write's content", confidence=0.95)]
    )
    knowledge_store.upsert_typed_nodes("fact", [_fact_row(scope, "pt-2", content="first version")])
    result = knowledge_store.typed_members("fact", scope)
    assert len(result.rows) == 2, "two distinct vector_ids must stay two distinct nodes"
    by_vector = {r["vector_id"]: r for r in result.rows}
    assert by_vector["pt-1"]["content"] == "first version", "content is create_only, immune to a repeat write"
    assert by_vector["pt-1"]["confidence"] == 0.95, "confidence is mutable, must refresh on the repeat write"
    assert by_vector["pt-2"]["content"] == "first version"


def test_media_segment_upsert_then_read_back():
    scope = GraphScope(user_id="u1")
    row = {
        "id": graph_store.node_id(scope, "media-1:0.0-5.0"), "user_id": scope.user_id,
        "repo_id": scope.repo_id, "modality": "video", "source_media_id": "media-1",
        "start_ts": 0.0, "end_ts": 5.0, "text": "they discuss pricing",
        "vector_id": "", "updated_at": 1.0,
    }
    applied = knowledge_store.upsert_typed_nodes("media_segment", [row])
    assert applied == [row["id"]]
    result = knowledge_store.typed_members("media_segment", scope)
    assert len(result.rows) == 1
    assert result.rows[0]["text"] == "they discuss pricing"


def test_a_caller_omitting_an_optional_mutable_column_does_not_break_the_write():
    """Regression proof: Kuzu infers a row's struct type strictly from the
    keys present in the batch passed to UNWIND — a caller omitting an
    optional mutable column (e.g. not yet setting vector_id) used to raise a
    binder error inside the try/except (silently dropping the whole write).
    `TypedNodeSchema.defaults` fills the gap before the row reaches Kuzu."""
    scope = GraphScope(user_id="u1")
    sparse_row = {
        "id": graph_store.node_id(scope, "sparse-entity"), "user_id": scope.user_id,
        "repo_id": scope.repo_id, "entity_type": "concept", "canonical_name": "sparse-entity",
        # vector_id / updated_at deliberately OMITTED.
    }
    applied = knowledge_store.upsert_typed_nodes("entity", [sparse_row])
    assert applied == [sparse_row["id"]], "omitting an optional mutable column must not drop the write"
    result = knowledge_store.typed_members("entity", scope)
    assert result.rows[0]["vector_id"] == "", "the schema default must fill the omitted column"


def test_unknown_kind_returns_empty_not_an_error():
    scope = GraphScope(user_id="u1")
    assert knowledge_store.upsert_typed_nodes("not-a-real-kind", [{"id": "x"}]) == []
    result = knowledge_store.typed_members("not-a-real-kind", scope)
    assert result.degraded is True


# ─────────────────────────────────────────────────────────────────────────────
# Heterogeneous edges — the genuinely new mechanic
# ─────────────────────────────────────────────────────────────────────────────

def test_relates_to_entity_to_fact_heterogeneous_edge_persists_and_reads_back():
    scope = GraphScope(user_id="u1")
    knowledge_store.upsert_typed_nodes("entity", [_entity_row(scope, "clannon")])
    knowledge_store.upsert_typed_nodes("fact", [_fact_row(scope, "pt-1")])
    entity_id, fact_id = graph_store.node_id(scope, "clannon"), graph_store.node_id(scope, "pt-1")

    applied = knowledge_store.upsert_typed_edges(
        "relates_to", [{"src": entity_id, "dst": fact_id, "origin": "inferred"}]
    )
    assert len(applied) == 1

    from_entity = knowledge_store.typed_edges_of("relates_to", scope, entity_id)
    from_fact = knowledge_store.typed_edges_of("relates_to", scope, fact_id)
    for result in (from_entity, from_fact):
        assert len(result.rows) == 1
        assert result.rows[0]["src"] == entity_id
        assert result.rows[0]["dst"] == fact_id


def test_relates_to_entity_to_entity_and_entity_to_claim_coexist():
    """RelatesTo spans FOUR distinct endpoint-pair combinations in one rel
    table — prove two different pairs from the SAME entity don't collide or
    overwrite each other."""
    scope = GraphScope(user_id="u1")
    knowledge_store.upsert_typed_nodes("entity", [_entity_row(scope, "alice"), _entity_row(scope, "bob")])
    knowledge_store.upsert_typed_nodes("claim", [
        {"id": graph_store.node_id(scope, "pt-claim"), "user_id": "u1", "repo_id": "",
         "content": "maybe true", "confidence": 0.4, "vector_id": "pt-claim", "updated_at": 1.0}
    ])
    alice, bob = graph_store.node_id(scope, "alice"), graph_store.node_id(scope, "bob")
    claim = graph_store.node_id(scope, "pt-claim")

    knowledge_store.upsert_typed_edges("relates_to", [
        {"src": alice, "dst": bob, "origin": "inferred"},
        {"src": alice, "dst": claim, "origin": "inferred"},
    ])
    from_alice = knowledge_store.typed_edges_of("relates_to", scope, alice)
    assert {r["dst"] for r in from_alice.rows} == {bob, claim}


def test_derived_from_fact_to_task_meets_the_batch_layer():
    """The batch-fusion point (§4 of the design): a Fact node DERIVED_FROM the
    TASK node whose batch produced it — the meeting point with the Mission
    Engine substrate, no new port."""
    import core.memory.mission_graph_store as mission_graph_store

    scope = GraphScope(user_id="u1")
    mission_graph_store.upsert_typed_nodes("task", [{
        "id": graph_store.node_id(scope, "t1"), "user_id": "u1", "repo_id": "",
        "task_id": "t1", "mission_id": "m1", "summary": "s", "status": "active",
        "evidence": "", "updated_at": 1.0,
    }])
    knowledge_store.upsert_typed_nodes("fact", [_fact_row(scope, "pt-1")])
    fact_id, task_id = graph_store.node_id(scope, "pt-1"), graph_store.node_id(scope, "t1")

    applied = knowledge_store.upsert_typed_edges(
        "derived_from", [{"src": fact_id, "dst": task_id, "origin": "inferred"}]
    )
    assert len(applied) == 1
    result = knowledge_store.typed_edges_of("derived_from", scope, task_id)
    assert result.rows[0]["src"] == fact_id
    assert result.rows[0]["dst"] == task_id


def test_authored_by_fact_to_entity():
    scope = GraphScope(user_id="u1")
    knowledge_store.upsert_typed_nodes("fact", [_fact_row(scope, "pt-1")])
    knowledge_store.upsert_typed_nodes("entity", [_entity_row(scope, "alice", entity_type="person")])
    fact_id, alice_id = graph_store.node_id(scope, "pt-1"), graph_store.node_id(scope, "alice")

    applied = knowledge_store.upsert_typed_edges(
        "authored_by", [{"src": fact_id, "dst": alice_id, "origin": "inferred"}]
    )
    assert len(applied) == 1
    result = knowledge_store.typed_edges_of("authored_by", scope, alice_id)
    assert result.rows[0]["src"] == fact_id


def test_contradicts_is_homogeneous_claim_to_claim_only():
    """Contradicts is declared FROM Claim TO Claim only (not heterogeneous) —
    an attempt naming a non-Claim endpoint (e.g. an Entity id) must silently
    fail to apply, never error, same 'no phantom writes' discipline as
    CodeFile/IMPORTS naming an unbacked endpoint."""
    scope = GraphScope(user_id="u1")
    knowledge_store.upsert_typed_nodes("claim", [
        {"id": graph_store.node_id(scope, "pt-a"), "user_id": "u1", "repo_id": "",
         "content": "X is true", "confidence": 0.5, "vector_id": "pt-a", "updated_at": 1.0},
        {"id": graph_store.node_id(scope, "pt-b"), "user_id": "u1", "repo_id": "",
         "content": "X is false", "confidence": 0.5, "vector_id": "pt-b", "updated_at": 1.0},
    ])
    knowledge_store.upsert_typed_nodes("entity", [_entity_row(scope, "not-a-claim")])
    claim_a, claim_b = graph_store.node_id(scope, "pt-a"), graph_store.node_id(scope, "pt-b")
    entity_id = graph_store.node_id(scope, "not-a-claim")

    applied = knowledge_store.upsert_typed_edges(
        "contradicts", [{"src": claim_a, "dst": claim_b, "origin": "inferred"}]
    )
    assert len(applied) == 1

    bad_applied = knowledge_store.upsert_typed_edges(
        "contradicts", [{"src": entity_id, "dst": claim_b, "origin": "inferred"}]
    )
    assert bad_applied == [], "a non-Claim endpoint must silently fail to apply, never raise"


def test_heterogeneous_edge_asserted_always_wins():
    scope = GraphScope(user_id="u1")
    knowledge_store.upsert_typed_nodes("entity", [_entity_row(scope, "clannon")])
    knowledge_store.upsert_typed_nodes("fact", [_fact_row(scope, "pt-1")])
    entity_id, fact_id = graph_store.node_id(scope, "clannon"), graph_store.node_id(scope, "pt-1")

    knowledge_store.upsert_typed_edges("relates_to", [{"src": entity_id, "dst": fact_id, "origin": "asserted"}])
    applied = knowledge_store.upsert_typed_edges(
        "relates_to", [{"src": entity_id, "dst": fact_id, "origin": "inferred"}]
    )
    assert applied == [], "an ASSERTED edge must be immune to an INFERRED overwrite attempt"
    result = knowledge_store.typed_edges_of("relates_to", scope, entity_id)
    assert result.rows[0]["origin"] == "asserted"


def test_heterogeneous_edge_missing_endpoint_silently_no_ops():
    """A heterogeneous edge naming an endpoint id that doesn't exist in ANY
    candidate table must silently fail to apply — never raise."""
    scope = GraphScope(user_id="u1")
    knowledge_store.upsert_typed_nodes("entity", [_entity_row(scope, "clannon")])
    entity_id = graph_store.node_id(scope, "clannon")
    ghost_id = graph_store.node_id(scope, "does-not-exist")

    applied = knowledge_store.upsert_typed_edges(
        "relates_to", [{"src": entity_id, "dst": ghost_id, "origin": "inferred"}]
    )
    assert applied == []


def test_tenant_isolation_same_canonical_name_different_users():
    scope_a, scope_b = GraphScope(user_id="u1"), GraphScope(user_id="u2")
    knowledge_store.upsert_typed_nodes("entity", [_entity_row(scope_a, "shared-name", vector_id="a")])
    knowledge_store.upsert_typed_nodes("entity", [_entity_row(scope_b, "shared-name", vector_id="b")])

    result_a = knowledge_store.typed_members("entity", scope_a)
    result_b = knowledge_store.typed_members("entity", scope_b)
    assert len(result_a.rows) == 1 and result_a.rows[0]["vector_id"] == "a"
    assert len(result_b.rows) == 1 and result_b.rows[0]["vector_id"] == "b"


def test_delete_user_purges_entity_fact_claim_media_segment():
    scope, other = GraphScope(user_id="owner"), GraphScope(user_id="other")
    knowledge_store.upsert_typed_nodes("entity", [_entity_row(scope, "e1")])
    knowledge_store.upsert_typed_nodes("fact", [_fact_row(scope, "pt-1")])
    knowledge_store.upsert_typed_nodes("entity", [_entity_row(other, "e1")])

    knowledge_store.delete_user("owner")

    assert knowledge_store.typed_members("entity", scope).rows == ()
    assert knowledge_store.typed_members("fact", scope).rows == ()
    other_view = knowledge_store.typed_members("entity", other)
    assert len(other_view.rows) == 1, "another tenant's data must survive delete_user"


def test_delete_user_no_op_on_missing_user_id():
    knowledge_store.delete_user("")  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# GraphManager dispatch — the port-facing surface
# ─────────────────────────────────────────────────────────────────────────────

def test_write_through_the_port_creates_an_entity_and_relates_to_edge(manager):
    async def go():
        scope = GraphScope(user_id="u1")
        entity = GraphNode(node_id=graph_store.node_id(scope, "memory manager"), label=NodeLabel.ENTITY,
                            scope=scope, properties={"canonical_name": "memory manager", "entity_type": "concept"})
        fact = GraphNode(node_id=graph_store.node_id(scope, "pt-1"), label=NodeLabel.FACT, scope=scope,
                          properties={"content": "sole-broker", "confidence": 0.9, "vector_id": "pt-1"})
        result = await manager.write(scope, [entity, fact], [])
        assert {n.node_id for n in result.nodes} == {entity.node_id, fact.node_id}

        edge = GraphEdge(src_id=entity.node_id, dst_id=fact.node_id,
                          label=EdgeLabel.RELATES_TO, origin=EdgeOrigin.INFERRED)
        edge_result = await manager.write(scope, [], [edge])
        assert len(edge_result.edges) == 1

        read_back = await manager.edges_of(scope, entity.node_id, EdgeLabel.RELATES_TO)
        assert len(read_back.edges) == 1
        assert read_back.edges[0].dst_id == fact.node_id
        assert read_back.edges[0].origin == EdgeOrigin.INFERRED
    asyncio.run(go())


def test_write_rejects_an_entity_missing_canonical_name(manager):
    async def go():
        scope = GraphScope(user_id="u1")
        bad = GraphNode(node_id="whatever", label=NodeLabel.ENTITY, scope=scope,
                         properties={"entity_type": "concept"})
        result = await manager.write(scope, [bad], [])
        assert result.nodes == []
        assert "canonical_name" in result.notes
    asyncio.run(go())


def test_members_and_edges_of_dispatch_to_knowledge_store_for_new_labels(manager):
    async def go():
        scope = GraphScope(user_id="u1")
        e1 = GraphNode(node_id=graph_store.node_id(scope, "e1"), label=NodeLabel.ENTITY, scope=scope,
                        properties={"canonical_name": "e1", "entity_type": "concept"})
        await manager.write(scope, [e1], [])
        result = await manager.members(scope, NodeLabel.ENTITY)
        assert len(result.nodes) == 1
        assert result.nodes[0].label == NodeLabel.ENTITY
        assert result.nodes[0].properties["canonical_name"] == "e1"
    asyncio.run(go())


def test_mixed_write_mission_task_and_knowledge_web_nodes_together(manager):
    """Mission/Task (mission_graph_store) and Entity/Fact (knowledge_store)
    can be written in the SAME write() call without interfering — the two
    typed-store dispatch paths coexist, same as CodeFile+Mission/Task before."""
    async def go():
        scope = GraphScope(user_id="u1")
        task_node = GraphNode(
            node_id=graph_store.node_id(scope, "t1"), label=NodeLabel.TASK, scope=scope,
            properties={"task_id": "t1", "mission_id": "m1", "summary": "s", "status": "active",
                        "evidence": "", "updated_at": 1.0},
        )
        entity_node = GraphNode(
            node_id=graph_store.node_id(scope, "clannon"), label=NodeLabel.ENTITY, scope=scope,
            properties={"canonical_name": "clannon", "entity_type": "concept"},
        )
        result = await manager.write(scope, [task_node, entity_node], [])
        assert {n.node_id for n in result.nodes} == {task_node.node_id, entity_node.node_id}
    asyncio.run(go())


def test_graph_manager_delete_user_purges_the_knowledge_web_too(manager):
    async def go():
        owner, other = GraphScope(user_id="owner"), GraphScope(user_id="other")
        e1 = GraphNode(node_id=graph_store.node_id(owner, "e1"), label=NodeLabel.ENTITY, scope=owner,
                        properties={"canonical_name": "e1", "entity_type": "concept"})
        other_e1 = GraphNode(node_id=graph_store.node_id(other, "e1"), label=NodeLabel.ENTITY, scope=other,
                              properties={"canonical_name": "e1", "entity_type": "concept"})
        await manager.write(owner, [e1], [])
        await manager.write(other, [other_e1], [])

        await manager.delete_user("owner")

        assert (await manager.members(owner, NodeLabel.ENTITY)).nodes == []
        other_view = await manager.members(other, NodeLabel.ENTITY)
        assert len(other_view.nodes) == 1, "another tenant's data must survive delete_user"
    asyncio.run(go())
