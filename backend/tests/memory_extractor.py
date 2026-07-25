"""
CB2/CB3 — the memory extractor: mirror an accepted FACT/ASSUMPTION/DECISION
memory onto the knowledge web (Entity + Fact/Claim graph twin, RelatesTo/
AuthoredBy edges) via `GraphManager.write()`. Gated on `kind` (not tier) and
on a genuinely fresh insert (a dedup-merge refresh reuses the same
memory_id/vector_id, so re-extracting is pure waste). Best-effort throughout:
a fault in extraction or in the graph write must never surface into the
memory write that already landed.

Three layers, each hermetic (no live Qdrant/Kuzu, no network, no paid keys):
  1. writer.extract_entities — the LLM call's own fail-closed contract
     (stubbed build_agent/run_structured, same seam as judge_supersession in
     tests/memory_supersession.py).
  2. write_policy._write_graph_twin — orchestration: correct node/edge shape
     per kind, entity convergence, participants -> AUTHORED_BY, unresolved
     relation pairs dropped, best-effort isolation.
  3. record_write_proposals end-to-end — the kind gate + fresh-insert-only
     gate, driven through the real write policy with fake store/embeddings/
     graph manager.

Run:
    cd backend && .venv/bin/python -m pytest tests/memory_extractor.py -v
"""
from __future__ import annotations

import asyncio

import core.memory.embeddings as emb_mod
import core.memory.graph_manager as graph_manager_mod
import core.memory.graph_store as graph_store_mod
import core.memory.store as store_mod
import core.memory.write_policy as write_policy_mod
import core.memory.writer as writer_mod
from core.memory.manager import MemoryManager
from core.memory.write_policy import _normalize_entity_name
from foundation import (
    EdgeLabel,
    EdgeOrigin,
    GraphEdge,
    GraphNode,
    GraphResult,
    GraphScope,
    MemoryKind,
    MemoryStore,
    MemoryWriteProposal,
    NodeLabel,
)

_DUMMY_VEC: list[float] = [0.1] * 768


def _embed_ok():
    async def embed(texts: list[str]) -> list[list[float]]:
        return [_DUMMY_VEC for _ in texts]
    return embed


def _no_hit(tier, user_id, vector, limit) -> list[dict]:
    return []


def _tripwire():
    async def fail(*a, **k):
        raise AssertionError("must not be called for this case")
    return fail


# ---------------------------------------------------------------------------
# 0. _normalize_entity_name
# ---------------------------------------------------------------------------

def test_normalize_entity_name_collapses_whitespace_and_case():
    assert _normalize_entity_name("  Memory   Manager ") == "memory manager"
    assert _normalize_entity_name("") == ""
    assert _normalize_entity_name("   ") == ""


# ---------------------------------------------------------------------------
# 1. writer.extract_entities — fail-closed LLM contract
# ---------------------------------------------------------------------------

def _stub_agent(monkeypatch, result=None, raises: Exception | None = None):
    monkeypatch.setattr(writer_mod, "build_agent", lambda *a, **kw: object())
    captured: dict = {}

    async def fake_run_structured(handle, prompt, **kw):
        captured["prompt"] = prompt
        if raises is not None:
            raise raises
        return result

    monkeypatch.setattr(writer_mod, "run_structured", fake_run_structured)
    return captured


def test_extract_entities_returns_entities_and_relates(monkeypatch):
    result = writer_mod.ExtractedEntities(
        entities=[writer_mod._ExtractedEntity(name="Clannon", entity_type="project")],
        relates=[],
    )
    captured = _stub_agent(monkeypatch, result=result)
    out = asyncio.run(writer_mod.extract_entities("Clannon uses Kuzu for its graph layer"))
    assert out.entities[0].name == "Clannon"
    assert "Clannon uses Kuzu" in captured["prompt"]


def test_extract_entities_empty_on_model_fault(monkeypatch):
    _stub_agent(monkeypatch, raises=RuntimeError("model unavailable"))
    out = asyncio.run(writer_mod.extract_entities("anything"))
    assert out.entities == [] and out.relates == []


def test_extract_entities_drops_blank_names(monkeypatch):
    result = writer_mod.ExtractedEntities(
        entities=[writer_mod._ExtractedEntity(name="  "), writer_mod._ExtractedEntity(name="Real Entity")],
        relates=[writer_mod._ExtractedRelation(a="", b="x")],
    )
    _stub_agent(monkeypatch, result=result)
    out = asyncio.run(writer_mod.extract_entities("content"))
    assert len(out.entities) == 1 and out.entities[0].name == "Real Entity"
    assert out.relates == []


def test_extract_entities_bounded_regardless_of_model_output(monkeypatch):
    result = writer_mod.ExtractedEntities(
        entities=[writer_mod._ExtractedEntity(name=f"e{i}") for i in range(20)],
        relates=[writer_mod._ExtractedRelation(a=f"e{i}", b=f"e{i + 1}") for i in range(20)],
    )
    _stub_agent(monkeypatch, result=result)
    out = asyncio.run(writer_mod.extract_entities("content"))
    assert len(out.entities) == writer_mod._MAX_ENTITIES
    assert len(out.relates) == writer_mod._MAX_RELATIONS


# ---------------------------------------------------------------------------
# 2. write_policy._write_graph_twin — orchestration
# ---------------------------------------------------------------------------

class _FakeGraphManager:
    def __init__(
        self, degraded: bool = False,
        claim_members: list[GraphNode] | None = None,
        entity_edges: dict[str, list[GraphEdge]] | None = None,
    ) -> None:
        self.calls: list[tuple] = []
        self.degraded = degraded
        # §3.2 fixtures: members(CLAIM) returns these; edges_of(entity_id, RELATES_TO) returns entity_edges[entity_id].
        self._claim_members = claim_members or []
        self._entity_edges = entity_edges or {}
        self.members_calls: list[tuple] = []
        self.edges_of_calls: list[tuple] = []

    async def write(self, scope, nodes, edges) -> GraphResult:
        self.calls.append((scope, nodes, edges))
        return GraphResult(nodes=nodes, edges=edges, degraded=self.degraded)

    async def members(self, scope, label, *, parent_id: str = "") -> GraphResult:
        self.members_calls.append((scope, label, parent_id))
        return GraphResult(nodes=list(self._claim_members))

    async def edges_of(self, scope, node_id, label) -> GraphResult:
        self.edges_of_calls.append((scope, node_id, label))
        return GraphResult(edges=list(self._entity_edges.get(node_id, [])))


def _fake_extract(entities=(), relates=()):
    async def extract(content: str) -> writer_mod.ExtractedEntities:
        return writer_mod.ExtractedEntities(entities=list(entities), relates=list(relates))
    return extract


def test_write_graph_twin_fact_kind_and_entity_relates_to_edge(monkeypatch):
    fake = _FakeGraphManager()
    monkeypatch.setattr(graph_manager_mod, "manager", fake)
    monkeypatch.setattr(writer_mod, "extract_entities", _fake_extract(
        entities=[writer_mod._ExtractedEntity(name="Clannon", entity_type="project")],
    ))

    asyncio.run(write_policy_mod._write_graph_twin("u1", "mem-1", "Clannon uses Kuzu", MemoryKind.FACT, ""))

    assert len(fake.calls) == 1
    scope, nodes, edges = fake.calls[0]
    assert scope == GraphScope(user_id="u1")
    labels = {n.label for n in nodes}
    assert labels == {NodeLabel.FACT, NodeLabel.ENTITY}
    fact_node = next(n for n in nodes if n.label == NodeLabel.FACT)
    assert fact_node.properties == {"content": "Clannon uses Kuzu", "vector_id": "mem-1"}
    assert len(edges) == 1 and edges[0].label == EdgeLabel.RELATES_TO


def test_write_graph_twin_decision_kind_also_becomes_fact_node(monkeypatch):
    """CB4: a DECISION is itself asserted, same epistemic weight as a
    source-backed fact — it must become a FACT node, not a CLAIM."""
    fake = _FakeGraphManager()
    monkeypatch.setattr(graph_manager_mod, "manager", fake)
    monkeypatch.setattr(writer_mod, "extract_entities", _fake_extract())

    asyncio.run(write_policy_mod._write_graph_twin("u1", "mem-2", "decided to ship X", MemoryKind.DECISION, ""))
    _, nodes, _ = fake.calls[0]
    assert nodes[0].label == NodeLabel.FACT


def test_write_graph_twin_assumption_kind_becomes_claim_node(monkeypatch):
    fake = _FakeGraphManager()
    monkeypatch.setattr(graph_manager_mod, "manager", fake)
    monkeypatch.setattr(writer_mod, "extract_entities", _fake_extract())

    asyncio.run(write_policy_mod._write_graph_twin("u1", "mem-3", "maybe true", MemoryKind.ASSUMPTION, ""))
    _, nodes, _ = fake.calls[0]
    assert nodes[0].label == NodeLabel.CLAIM


def test_write_graph_twin_participants_become_authored_by_edges(monkeypatch):
    fake = _FakeGraphManager()
    monkeypatch.setattr(graph_manager_mod, "manager", fake)
    monkeypatch.setattr(writer_mod, "extract_entities", _fake_extract())

    asyncio.run(write_policy_mod._write_graph_twin("u1", "mem-4", "decided X", MemoryKind.DECISION, "Jane, Bob"))
    _, nodes, edges = fake.calls[0]
    entity_names = {n.properties["canonical_name"] for n in nodes if n.label == NodeLabel.ENTITY}
    assert entity_names == {"jane", "bob"}
    assert len(edges) == 2 and all(e.label == EdgeLabel.AUTHORED_BY for e in edges)


def test_write_graph_twin_relates_pair_between_two_extracted_entities(monkeypatch):
    fake = _FakeGraphManager()
    monkeypatch.setattr(graph_manager_mod, "manager", fake)
    monkeypatch.setattr(writer_mod, "extract_entities", _fake_extract(
        entities=[writer_mod._ExtractedEntity(name="Jane"), writer_mod._ExtractedEntity(name="Memory Manager")],
        relates=[writer_mod._ExtractedRelation(a="Jane", b="Memory Manager")],
    ))

    asyncio.run(write_policy_mod._write_graph_twin("u1", "mem-5", "Jane owns the Memory Manager", MemoryKind.FACT, ""))
    _, nodes, edges = fake.calls[0]
    relates_edges = [e for e in edges if e.label == EdgeLabel.RELATES_TO]
    # 2 entity->fact edges + 1 entity->entity edge
    assert len(relates_edges) == 3


def test_write_graph_twin_relates_pair_with_unresolved_entity_is_dropped(monkeypatch):
    fake = _FakeGraphManager()
    monkeypatch.setattr(graph_manager_mod, "manager", fake)
    monkeypatch.setattr(writer_mod, "extract_entities", _fake_extract(
        entities=[writer_mod._ExtractedEntity(name="Jane")],
        relates=[writer_mod._ExtractedRelation(a="Jane", b="Ghost")],
    ))

    asyncio.run(write_policy_mod._write_graph_twin("u1", "mem-6", "content", MemoryKind.FACT, ""))
    _, nodes, edges = fake.calls[0]
    # only Jane -> fact RELATES_TO; nothing for the never-extracted "Ghost"
    assert len(edges) == 1


def test_write_graph_twin_entity_convergence_same_name_case_and_whitespace(monkeypatch):
    fake = _FakeGraphManager()
    monkeypatch.setattr(graph_manager_mod, "manager", fake)
    monkeypatch.setattr(writer_mod, "extract_entities", _fake_extract(
        entities=[writer_mod._ExtractedEntity(name="Jane"), writer_mod._ExtractedEntity(name="  jane ")],
    ))

    asyncio.run(write_policy_mod._write_graph_twin("u1", "mem-7", "content", MemoryKind.FACT, ""))
    _, nodes, _ = fake.calls[0]
    entity_nodes = [n for n in nodes if n.label == NodeLabel.ENTITY]
    assert len(entity_nodes) == 1, "two mentions of the same name must converge onto one node"


def test_write_graph_twin_no_entities_still_writes_the_fact_node_alone(monkeypatch):
    fake = _FakeGraphManager()
    monkeypatch.setattr(graph_manager_mod, "manager", fake)
    monkeypatch.setattr(writer_mod, "extract_entities", _fake_extract())

    asyncio.run(write_policy_mod._write_graph_twin("u1", "mem-8", "content", MemoryKind.FACT, ""))
    _, nodes, edges = fake.calls[0]
    assert len(nodes) == 1 and nodes[0].label == NodeLabel.FACT
    assert edges == []


def test_write_graph_twin_extraction_fault_never_raises_and_never_writes(monkeypatch):
    fake = _FakeGraphManager()
    monkeypatch.setattr(graph_manager_mod, "manager", fake)

    async def raising_extract(content):
        raise RuntimeError("boom")
    monkeypatch.setattr(writer_mod, "extract_entities", raising_extract)

    asyncio.run(write_policy_mod._write_graph_twin("u1", "mem-9", "content", MemoryKind.FACT, ""))
    assert fake.calls == [], "a failed extraction must never reach the graph write"


def test_write_graph_twin_write_fault_never_raises(monkeypatch):
    class _RaisingManager:
        async def write(self, scope, nodes, edges):
            raise RuntimeError("kuzu down")
    monkeypatch.setattr(graph_manager_mod, "manager", _RaisingManager())
    monkeypatch.setattr(writer_mod, "extract_entities", _fake_extract())

    asyncio.run(write_policy_mod._write_graph_twin("u1", "mem-10", "content", MemoryKind.FACT, ""))  # must not raise


def test_write_graph_twin_degraded_result_is_honestly_absorbed_not_hidden(monkeypatch):
    fake = _FakeGraphManager(degraded=True)
    monkeypatch.setattr(graph_manager_mod, "manager", fake)
    monkeypatch.setattr(writer_mod, "extract_entities", _fake_extract())

    asyncio.run(write_policy_mod._write_graph_twin("u1", "mem-11", "content", MemoryKind.FACT, ""))
    assert len(fake.calls) == 1  # still attempted; degradation is logged, not swallowed silently upstream


# ---------------------------------------------------------------------------
# 3. record_write_proposals end-to-end — the kind gate + fresh-insert gate
# ---------------------------------------------------------------------------

def _p(kind: MemoryKind = MemoryKind.UNSPECIFIED, store_tier: MemoryStore = MemoryStore.SEMANTIC) -> MemoryWriteProposal:
    return MemoryWriteProposal(store=store_tier, content="some content", confidence=0.9, kind=kind)


def test_graph_twin_triggered_for_fact_kind_on_fresh_insert(monkeypatch):
    monkeypatch.setattr(emb_mod, "embed", _embed_ok())
    monkeypatch.setattr(store_mod, "search", _no_hit)
    monkeypatch.setattr(store_mod, "upsert", lambda *a, **k: "new-id")
    fake = _FakeGraphManager()
    monkeypatch.setattr(graph_manager_mod, "manager", fake)
    monkeypatch.setattr(writer_mod, "extract_entities", _fake_extract())

    result = asyncio.run(MemoryManager().record_write_proposals("u1", "sess", [_p(kind=MemoryKind.FACT)]))
    assert len(result) == 1
    assert len(fake.calls) == 1


def test_graph_twin_triggered_for_decision_kind_regardless_of_tier(monkeypatch):
    """The gate is kind-based, not tier-based — a DECISION proposal (CB4
    settles it as EPISODIC) must still get a graph twin."""
    monkeypatch.setattr(emb_mod, "embed", _embed_ok())
    monkeypatch.setattr(store_mod, "search", _no_hit)
    monkeypatch.setattr(store_mod, "upsert", lambda *a, **k: "new-id")
    fake = _FakeGraphManager()
    monkeypatch.setattr(graph_manager_mod, "manager", fake)
    monkeypatch.setattr(writer_mod, "extract_entities", _fake_extract())

    result = asyncio.run(MemoryManager().record_write_proposals(
        "u1", "sess", [_p(kind=MemoryKind.DECISION, store_tier=MemoryStore.EPISODIC)]
    ))
    assert len(result) == 1
    assert len(fake.calls) == 1


def test_graph_twin_not_triggered_for_unspecified_kind(monkeypatch):
    monkeypatch.setattr(emb_mod, "embed", _embed_ok())
    monkeypatch.setattr(store_mod, "search", _no_hit)
    monkeypatch.setattr(store_mod, "upsert", lambda *a, **k: "new-id")
    fake = _FakeGraphManager()
    monkeypatch.setattr(graph_manager_mod, "manager", fake)
    monkeypatch.setattr(writer_mod, "extract_entities", _tripwire())

    result = asyncio.run(MemoryManager().record_write_proposals("u1", "sess", [_p(kind=MemoryKind.UNSPECIFIED)]))
    assert len(result) == 1
    assert fake.calls == []


def test_graph_twin_not_triggered_on_a_dedup_merge_refresh(monkeypatch):
    """A dedup-merge reuses the existing memory_id/vector_id — re-extracting
    would be pure waste (Fact/Claim's `content` is create_only anyway)."""
    monkeypatch.setattr(emb_mod, "embed", _embed_ok())
    monkeypatch.setattr(store_mod, "search", lambda tier, user_id, vector, limit: [
        {"id": "existing-id", "score": 1.0, "content": "old", "confidence": 0.5}
    ])
    monkeypatch.setattr(store_mod, "upsert", lambda *a, **k: "existing-id")
    fake = _FakeGraphManager()
    monkeypatch.setattr(graph_manager_mod, "manager", fake)
    monkeypatch.setattr(writer_mod, "extract_entities", _tripwire())

    result = asyncio.run(MemoryManager().record_write_proposals("u1", "sess", [_p(kind=MemoryKind.FACT)]))
    assert len(result) == 1
    assert fake.calls == []


# ---------------------------------------------------------------------------
# 4. writer.judge_contradiction — fail-closed LLM contract (§3.2)
# ---------------------------------------------------------------------------

def test_judge_contradiction_true_when_confident_and_contradicts(monkeypatch):
    captured = _stub_agent(
        monkeypatch,
        result=writer_mod._ContradictionVerdict(contradicts=True, confident=True, rationale="opposite claims"),
    )
    result = asyncio.run(writer_mod.judge_contradiction("X is true", "X is false"))
    assert result is True
    assert "X is true" in captured["prompt"] and "X is false" in captured["prompt"]


def test_judge_contradiction_false_when_not_confident(monkeypatch):
    _stub_agent(monkeypatch, result=writer_mod._ContradictionVerdict(contradicts=True, confident=False))
    assert asyncio.run(writer_mod.judge_contradiction("a", "b")) is False, "contradicts=True but NOT confident must still fail closed"


def test_judge_contradiction_false_when_not_contradicts(monkeypatch):
    _stub_agent(monkeypatch, result=writer_mod._ContradictionVerdict(contradicts=False, confident=True))
    assert asyncio.run(writer_mod.judge_contradiction("a", "b")) is False


def test_judge_contradiction_false_on_model_fault(monkeypatch):
    _stub_agent(monkeypatch, raises=RuntimeError("model unavailable"))
    assert asyncio.run(writer_mod.judge_contradiction("a", "b")) is False


# ---------------------------------------------------------------------------
# 5. write_policy._judge_contradictions — the §3.2 candidate funnel
# ---------------------------------------------------------------------------

def _claim_node(node_id: str, content: str, scope: GraphScope) -> GraphNode:
    return GraphNode(node_id=node_id, label=NodeLabel.CLAIM, scope=scope, properties={"content": content})


def test_judge_contradictions_finds_candidate_via_shared_entity_and_returns_edge(monkeypatch):
    scope = GraphScope(user_id="u1")
    entity_id = "e1"
    candidate = _claim_node("old-claim", "old claim", scope)
    fake = _FakeGraphManager(
        claim_members=[candidate],
        entity_edges={entity_id: [GraphEdge(src_id=entity_id, dst_id="old-claim", label=EdgeLabel.RELATES_TO, origin=EdgeOrigin.INFERRED)]},
    )
    monkeypatch.setattr(graph_manager_mod, "manager", fake)

    async def fake_judge(new, existing):
        return True
    monkeypatch.setattr(writer_mod, "judge_contradiction", fake_judge)

    edges = asyncio.run(write_policy_mod._judge_contradictions(scope, "new-claim", {entity_id}, "new content"))
    assert len(edges) == 1
    assert edges[0].src_id == "new-claim" and edges[0].dst_id == "old-claim"
    assert edges[0].label == EdgeLabel.CONTRADICTS


def test_judge_contradictions_no_edge_when_judge_says_no(monkeypatch):
    scope = GraphScope(user_id="u1")
    entity_id = "e1"
    fake = _FakeGraphManager(
        claim_members=[_claim_node("old-claim", "old claim", scope)],
        entity_edges={entity_id: [GraphEdge(src_id=entity_id, dst_id="old-claim", label=EdgeLabel.RELATES_TO, origin=EdgeOrigin.INFERRED)]},
    )
    monkeypatch.setattr(graph_manager_mod, "manager", fake)

    async def fake_judge(new, existing):
        return False
    monkeypatch.setattr(writer_mod, "judge_contradiction", fake_judge)

    edges = asyncio.run(write_policy_mod._judge_contradictions(scope, "new-claim", {entity_id}, "new content"))
    assert edges == []


def test_judge_contradictions_excludes_self_from_candidates(monkeypatch):
    scope = GraphScope(user_id="u1")
    entity_id, fact_id = "e1", "new-claim"
    fake = _FakeGraphManager(
        claim_members=[_claim_node(fact_id, "new content", scope)],  # the just-written node itself
        entity_edges={entity_id: [GraphEdge(src_id=entity_id, dst_id=fact_id, label=EdgeLabel.RELATES_TO, origin=EdgeOrigin.INFERRED)]},
    )
    monkeypatch.setattr(graph_manager_mod, "manager", fake)
    monkeypatch.setattr(writer_mod, "judge_contradiction", _tripwire())

    edges = asyncio.run(write_policy_mod._judge_contradictions(scope, fact_id, {entity_id}, "new content"))
    assert edges == []


def test_judge_contradictions_no_candidates_never_calls_the_judge(monkeypatch):
    scope = GraphScope(user_id="u1")
    fake = _FakeGraphManager()  # no claim_members at all
    monkeypatch.setattr(graph_manager_mod, "manager", fake)
    monkeypatch.setattr(writer_mod, "judge_contradiction", _tripwire())

    edges = asyncio.run(write_policy_mod._judge_contradictions(scope, "new-claim", {"e1"}, "new content"))
    assert edges == []
    assert fake.edges_of_calls == [], "must short-circuit before even looking up entity edges when there are no claims at all"


def test_judge_contradictions_bounded_to_max_candidates(monkeypatch):
    scope = GraphScope(user_id="u1")
    entity_id = "e1"
    n = 10
    claim_nodes = [_claim_node(f"c{i}", f"claim {i}", scope) for i in range(n)]
    edges_fixture = [GraphEdge(src_id=entity_id, dst_id=f"c{i}", label=EdgeLabel.RELATES_TO, origin=EdgeOrigin.INFERRED) for i in range(n)]
    fake = _FakeGraphManager(claim_members=claim_nodes, entity_edges={entity_id: edges_fixture})
    monkeypatch.setattr(graph_manager_mod, "manager", fake)

    judged: list[str] = []

    async def counting_judge(new, existing):
        judged.append(existing)
        return False
    monkeypatch.setattr(writer_mod, "judge_contradiction", counting_judge)

    asyncio.run(write_policy_mod._judge_contradictions(scope, "new-claim", {entity_id}, "new content"))
    assert len(judged) == write_policy_mod._MAX_CONTRADICTION_CANDIDATES


def test_judge_contradictions_one_candidate_fault_does_not_stop_the_rest(monkeypatch):
    scope = GraphScope(user_id="u1")
    entity_id = "e1"
    claim_nodes = [_claim_node("c1", "claim 1", scope), _claim_node("c2", "claim 2", scope)]
    edges_fixture = [
        GraphEdge(src_id=entity_id, dst_id="c1", label=EdgeLabel.RELATES_TO, origin=EdgeOrigin.INFERRED),
        GraphEdge(src_id=entity_id, dst_id="c2", label=EdgeLabel.RELATES_TO, origin=EdgeOrigin.INFERRED),
    ]
    fake = _FakeGraphManager(claim_members=claim_nodes, entity_edges={entity_id: edges_fixture})
    monkeypatch.setattr(graph_manager_mod, "manager", fake)

    async def flaky_judge(new, existing):
        if existing == "claim 1":
            raise RuntimeError("boom")
        return True
    monkeypatch.setattr(writer_mod, "judge_contradiction", flaky_judge)

    edges = asyncio.run(write_policy_mod._judge_contradictions(scope, "new-claim", {entity_id}, "new content"))
    assert len(edges) == 1
    assert edges[0].dst_id == "c2"


# ---------------------------------------------------------------------------
# 6. _write_graph_twin <-> contradiction check integration (§3.2)
# ---------------------------------------------------------------------------

def test_write_graph_twin_fact_kind_never_triggers_contradiction_check(monkeypatch):
    """CONTRADICTS is homogeneous Claim<->Claim — a FACT (or DECISION) twin
    must never even look."""
    fake = _FakeGraphManager()
    monkeypatch.setattr(graph_manager_mod, "manager", fake)
    monkeypatch.setattr(writer_mod, "extract_entities", _fake_extract(
        entities=[writer_mod._ExtractedEntity(name="Clannon")],
    ))

    asyncio.run(write_policy_mod._write_graph_twin("u1", "mem-fact", "content", MemoryKind.FACT, ""))

    assert fake.members_calls == [] and fake.edges_of_calls == []


def test_write_graph_twin_assumption_kind_with_no_entities_skips_contradiction_check(monkeypatch):
    fake = _FakeGraphManager()
    monkeypatch.setattr(graph_manager_mod, "manager", fake)
    monkeypatch.setattr(writer_mod, "extract_entities", _fake_extract())  # no entities extracted

    asyncio.run(write_policy_mod._write_graph_twin("u1", "mem-noent", "content", MemoryKind.ASSUMPTION, ""))

    assert fake.members_calls == [], "no RELATES_TO entity means no candidate band to search"


def test_write_graph_twin_assumption_kind_with_entity_checks_for_contradictions(monkeypatch):
    fake = _FakeGraphManager()  # no pre-existing claims -> short-circuits after members()
    monkeypatch.setattr(graph_manager_mod, "manager", fake)
    monkeypatch.setattr(writer_mod, "extract_entities", _fake_extract(
        entities=[writer_mod._ExtractedEntity(name="Clannon")],
    ))
    monkeypatch.setattr(writer_mod, "judge_contradiction", _tripwire())  # must never be reached: no candidates exist

    asyncio.run(write_policy_mod._write_graph_twin("u1", "mem-assume", "content", MemoryKind.ASSUMPTION, ""))

    assert len(fake.members_calls) == 1
    assert fake.members_calls[0][1] == NodeLabel.CLAIM
    assert fake.edges_of_calls == []  # short-circuited: no claims exist at all yet


def test_write_graph_twin_writes_contradicts_edge_when_judge_confirms(monkeypatch):
    scope = GraphScope(user_id="u1")
    entity_id = graph_store_mod.node_id(scope, "clannon")  # exact id _write_graph_twin mints for "Clannon"
    existing_claim_id = "u1||mem-old"
    fake = _FakeGraphManager(
        claim_members=[_claim_node(existing_claim_id, "old claim", scope)],
        entity_edges={entity_id: [GraphEdge(src_id=entity_id, dst_id=existing_claim_id, label=EdgeLabel.RELATES_TO, origin=EdgeOrigin.INFERRED)]},
    )
    monkeypatch.setattr(graph_manager_mod, "manager", fake)
    monkeypatch.setattr(writer_mod, "extract_entities", _fake_extract(
        entities=[writer_mod._ExtractedEntity(name="Clannon")],
    ))

    async def fake_judge(new, existing):
        return True
    monkeypatch.setattr(writer_mod, "judge_contradiction", fake_judge)

    asyncio.run(write_policy_mod._write_graph_twin("u1", "mem-new", "new claim", MemoryKind.ASSUMPTION, ""))

    assert len(fake.calls) == 2, "the node/RELATES_TO write, then a separate CONTRADICTS-only edge write"
    _, contra_nodes, contra_edges = fake.calls[1]
    assert contra_nodes == []
    assert len(contra_edges) == 1
    assert contra_edges[0].label == EdgeLabel.CONTRADICTS
    assert contra_edges[0].dst_id == existing_claim_id


def test_write_graph_twin_contradiction_check_fault_never_raises_and_leaves_the_twin_intact(monkeypatch):
    class _RaisingMembersManager(_FakeGraphManager):
        async def members(self, scope, label, *, parent_id=""):
            raise RuntimeError("kuzu down")

    fake = _RaisingMembersManager()
    monkeypatch.setattr(graph_manager_mod, "manager", fake)
    monkeypatch.setattr(writer_mod, "extract_entities", _fake_extract(
        entities=[writer_mod._ExtractedEntity(name="Clannon")],
    ))

    asyncio.run(write_policy_mod._write_graph_twin("u1", "mem-fault", "content", MemoryKind.ASSUMPTION, ""))  # must not raise

    assert len(fake.calls) == 1, "the graph twin itself must still have landed despite the contradiction check faulting"
