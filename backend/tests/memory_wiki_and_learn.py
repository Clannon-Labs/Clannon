"""Wiki-as-text hydration and the legacy curator caller shim."""

import asyncio
from types import SimpleNamespace

from foundation import HydrationRequest, MemoryPort, MemoryStore
from core.memory.manager import MemoryManager
import core.memory.hydration as hydration_mod


def _req(query="", wiki=(), user_id="u"):
    return HydrationRequest(
        session_id="s", user_id=user_id,
        normalized=SimpleNamespace(content=query) if query else None,
        wiki=wiki,
    )


def test_manager_satisfies_memory_port():
    # runtime_checkable: manager exposes hydrate/process/list/delete.
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


def test_learn_routes_neutral_turn_to_manager_curator(monkeypatch):
    m = MemoryManager()
    captured = {}

    async def fake_process(turn):
        captured["turn"] = turn
        return []

    monkeypatch.setattr(m, "process_turn", fake_process)

    asyncio.run(m.learn("u", "s", task="t", answer="a", findings=["f"]))
    turn = captured["turn"]
    assert (turn.user_id, turn.session_id, turn.request, turn.response) == ("u", "s", "t", "a")
    assert turn.findings == ("f",)


def test_learn_is_best_effort_when_curator_fails(monkeypatch):
    m = MemoryManager()

    async def boom(_turn):
        raise RuntimeError("model down")
    monkeypatch.setattr(m, "process_turn", boom)

    # Compatibility caller still cannot sink an already-delivered turn.
    asyncio.run(m.learn("u", "s", task="t", answer="a", findings=[]))
