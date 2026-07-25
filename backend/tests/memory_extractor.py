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
import core.memory.store as store_mod
import core.memory.write_policy as write_policy_mod
import core.memory.writer as writer_mod
from core.memory.manager import MemoryManager
from core.memory.write_policy import _normalize_entity_name
from foundation import EdgeLabel, GraphResult, GraphScope, MemoryKind, MemoryStore, MemoryWriteProposal, NodeLabel

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
    def __init__(self, degraded: bool = False) -> None:
        self.calls: list[tuple] = []
        self.degraded = degraded

    async def write(self, scope, nodes, edges) -> GraphResult:
        self.calls.append((scope, nodes, edges))
        return GraphResult(nodes=nodes, edges=edges, degraded=self.degraded)


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
