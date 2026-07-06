"""Wiki-as-text hydration and the semantic/procedural memory agent."""

import asyncio
from types import SimpleNamespace

from foundation import HydrationRequest, MemoryPort, MemoryStore, MemoryWriteProposal
from core.memory.manager import MemoryManager
import core.memory.hydration as hydration_mod
import core.memory.writer as writer_mod


def _req(query="", wiki=(), user_id="u"):
    return HydrationRequest(
        session_id="s", user_id=user_id,
        normalized=SimpleNamespace(content=query) if query else None,
        wiki=wiki,
    )


def test_manager_satisfies_memory_port():
    # runtime_checkable: the manager must expose hydrate + record + learn
    assert isinstance(MemoryManager(), MemoryPort)


def test_select_wiki_ranks_by_relevance_and_bounds_budget():
    wiki = (
        ("Meridian Skincare", "US DTC skincare brand, ceramide serum, CMO is Priya."),
        ("Acme Legal", "UK law firm, wants a docs tool, hates jargon."),
    )
    items = hydration_mod._select_wiki(wiki, "what is meridian's hero product?", 10_000)
    assert items, "relevant wiki should be selected"
    assert "Meridian" in items[0].content  # the lexically-overlapping entry leads
    assert all(i.store is MemoryStore.WIKI and i.trust == 3 for i in items)

    # a tiny budget admits at most one entry
    tight = hydration_mod._select_wiki(wiki, "meridian acme", 5)
    assert len(tight) <= 1


def test_hydrate_loads_wiki_as_text_without_vectors():
    # empty query => no embedding/vector search; wiki should still hydrate as text
    m = MemoryManager()
    pkg = asyncio.run(m.hydrate(_req(query="", wiki=(("Client", "Important standing fact."),))))
    assert pkg.items, "wiki should hydrate even with no query/vectors"
    assert pkg.items[0].store is MemoryStore.WIKI
    assert not pkg.degraded


def test_learn_records_distilled_proposals(monkeypatch):
    m = MemoryManager()

    async def fake_distill(task, answer, findings):
        return [
            MemoryWriteProposal(store=MemoryStore.SEMANTIC, content="A durable fact.", confidence=0.9),
            MemoryWriteProposal(store=MemoryStore.PROCEDURAL, content="A working pattern.", confidence=0.8),
        ]
    monkeypatch.setattr(writer_mod, "distill", fake_distill)

    captured = {}
    async def fake_record(user_id, session_id, proposals):
        captured["proposals"] = proposals
    monkeypatch.setattr(m, "record_write_proposals", fake_record)

    asyncio.run(m.learn("u", "s", task="t", answer="a", findings=["f"]))
    stores = {p.store for p in captured["proposals"]}
    assert stores == {MemoryStore.SEMANTIC, MemoryStore.PROCEDURAL}


def test_learn_is_best_effort_when_distill_fails(monkeypatch):
    m = MemoryManager()

    async def boom(task, answer, findings):
        raise RuntimeError("model down")
    monkeypatch.setattr(writer_mod, "distill", boom)

    called = {"n": 0}
    async def fake_record(*a, **k):
        called["n"] += 1
    monkeypatch.setattr(m, "record_write_proposals", fake_record)

    # must not raise, and must not record anything on failure
    asyncio.run(m.learn("u", "s", task="t", answer="a", findings=[]))
    assert called["n"] == 0
