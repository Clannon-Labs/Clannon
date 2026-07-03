"""memory.search: a READ-ONLY, user-scoped recall tool. The tool formats a
HydrationPackage into hits; the handler-injected MemorySearcher builds the scoped
request and degrades (never raises) when memory is down."""

import asyncio

from foundation import HydrationPackage, MemoryItem, MemoryStore, VrakshaContext
from registry.capabilities import discover, registry
from registry.capabilities.handler.tools import MemorySearcher
from tools.memory_search import MemSearchIn, MemorySearchTool


class _FakeMemory:
    """Stands in for the injected MemorySearcher."""
    def __init__(self, pkg):
        self._pkg = pkg
    async def search(self, query):
        return self._pkg


# ---- the tool formats recall into hits -------------------------------------


def test_memory_search_formats_hits_by_tier():
    pkg = HydrationPackage(items=[
        MemoryItem(store=MemoryStore.WIKI, content="client likes terse reports", score=0.9, trust=5),
        MemoryItem(store=MemoryStore.EPISODIC, content="last run found X", score=0.7, trust=2),
    ])
    out = asyncio.run(MemorySearchTool().run(MemSearchIn(query="client prefs"), _FakeMemory(pkg)))
    assert [(h.store, h.trust) for h in out.hits] == [("wiki", 5), ("episodic", 2)]
    assert out.degraded is False and out.note == ""


def test_memory_search_respects_max_results():
    pkg = HydrationPackage(items=[MemoryItem(store=MemoryStore.SEMANTIC, content=str(i)) for i in range(10)])
    out = asyncio.run(MemorySearchTool().run(MemSearchIn(query="q", max_results=3), _FakeMemory(pkg)))
    assert len(out.hits) == 3


def test_memory_search_reports_degraded():
    out = asyncio.run(MemorySearchTool().run(
        MemSearchIn(query="x"), _FakeMemory(HydrationPackage(degraded=True, notes="store down"))))
    assert out.hits == [] and out.degraded is True and "down" in out.note


def test_memory_search_notes_empty_memory():
    out = asyncio.run(MemorySearchTool().run(MemSearchIn(query="x"), _FakeMemory(HydrationPackage())))
    assert out.hits == [] and out.degraded is False and "no relevant memory" in out.note


# ---- the injected searcher: user-scoped request + soft-fail ----------------


def test_searcher_builds_user_scoped_request(monkeypatch):
    captured = {}
    async def fake_hydrate(req):
        captured["req"] = req
        return HydrationPackage(items=[])
    monkeypatch.setattr("core.memory.manager.hydrate", fake_hydrate)

    ctx = VrakshaContext.new(session_id="s1", user_id="u1")
    ctx.wiki_entries = [{"title": "Acme", "content": "prefers bullet points"}]
    asyncio.run(MemorySearcher(ctx).search("how does acme like reports"))

    req = captured["req"]
    assert req.user_id == "u1" and req.session_id == "s1"        # MANDATORY user scope
    assert req.normalized.content == "how does acme like reports"
    assert req.wiki == (("Acme", "prefers bullet points"),)     # the run's wiki, as text


def test_searcher_degrades_instead_of_raising(monkeypatch):
    async def boom(req):
        raise RuntimeError("qdrant unreachable")
    monkeypatch.setattr("core.memory.manager.hydrate", boom)
    pkg = asyncio.run(MemorySearcher(VrakshaContext.new(session_id="s", user_id="u")).search("x"))
    assert pkg.degraded is True and pkg.items == []             # a memory fault never sinks the tool/run


# ---- registered + granted --------------------------------------------------


def test_memory_search_registered_for_the_orchestrator_only():
    discover()
    from foundation import PermissionLevel
    tool = registry.get_tool("memory.search")
    assert tool is not None and tool.permission == PermissionLevel.READ      # read-only
    assert getattr(tool.impl, "wants_memory", False) is True
    # sole-broker (§7.3): the tool stays registered as the ORCHESTRATOR's door;
    # no expert holds it (experts get their context pushed via ExpertEnv.hydration)
    assert "memory.search" not in registry.get_expert("web.research").tool_grants
    assert "memory.search" not in {b.key for b in registry.broken()}
