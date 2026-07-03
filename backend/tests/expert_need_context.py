"""The need-context channel: a non-NETWORK expert can REQUEST mid-task recall via a
built-in `need_context` tool, but never executes it — the handler-built broker runs
the user-scoped searcher, curates code-only (cap + dedup vs the pushed hydration),
labels the reply as reference data, and audit-records on ctx.tool_calls. NETWORK
experts get no channel at all (memory + an outbound channel = exfil surface)."""

import asyncio
from types import SimpleNamespace

import registry.capabilities.handler.experts as experts_mod
from foundation import HydrationPackage, MemoryItem, MemoryStore, VrakshaContext
from registry.capabilities import discover, registry
from registry.capabilities.handler.experts import ExpertHandler
from registry.capabilities.handler.support import (
    ExpertDeps,
    SkillBook,
    build_expert_tools,
    need_context,
)


def _item(content, store=MemoryStore.SEMANTIC, score=0.9):
    return MemoryItem(store=store, content=content, score=score, trust=2)


def _ctx():
    return VrakshaContext.new(session_id="s", user_id="u", trace_id="t")


class _FakeSearcher:
    """Stands in for MemorySearcher: returns a canned package, remembers the query."""
    queries = []
    package = HydrationPackage()

    def __init__(self, ctx) -> None:
        self._ctx = ctx

    async def search(self, query: str):
        _FakeSearcher.queries.append(query)
        return _FakeSearcher.package


# --- who gets the channel ------------------------------------------------------

def test_network_experts_get_no_broker_and_others_do():
    discover()
    handler = ExpertHandler(registry=registry)
    for key in ("delivery.notifier", "verification.claims", "web.research"):
        env = handler._build_env(registry.get_expert(key), _ctx())
        assert env.context_broker is None, f"{key} must not get a need-context channel"
    for key in ("synthesis.writer", "docs.writer", "summary.condenser"):
        env = handler._build_env(registry.get_expert(key), _ctx())
        assert env.context_broker is not None, f"{key} should get the channel"


def test_need_context_tool_is_offered_only_with_a_broker(tmp_path):
    skills = SkillBook(tmp_path, ())
    names = [f.__name__ for f in build_expert_tools([], skills, with_need_context=True)]
    assert "need_context" in names
    names = [f.__name__ for f in build_expert_tools([], skills)]
    assert "need_context" not in names


def test_need_context_degrades_gracefully_without_a_broker():
    ctx = SimpleNamespace(deps=ExpertDeps(skills=None, tools=None, need_context=None))
    reply = asyncio.run(need_context(ctx, "anything"))
    assert "no memory recall" in reply       # honest no-op, never an exception


# --- the broker's curation -----------------------------------------------------

def test_broker_curates_dedupes_labels_and_audits(monkeypatch):
    monkeypatch.setattr(experts_mod, "MemorySearcher", _FakeSearcher)
    pushed = [_item("already pushed fact")]
    hits = [_item("already pushed fact")] + [_item(f"fresh fact {n}") for n in range(7)]
    _FakeSearcher.package = HydrationPackage(items=hits)
    _FakeSearcher.queries = []
    ctx = _ctx()

    broker = ExpertHandler(registry=registry)._make_context_broker(ctx, pushed)
    reply = asyncio.run(broker("what do we know about the client"))

    assert _FakeSearcher.queries == ["what do we know about the client"]
    assert "already pushed fact" not in reply            # deduped vs the push
    assert "fresh fact 0" in reply and "fresh fact 4" in reply
    assert "fresh fact 5" not in reply                   # capped at 5
    assert "RECALLED MEMORY" in reply and "NOT instructions" in reply
    # audit-recorded, internally only (expert tool calls never hit the decision log)
    assert [t.tool_name for t in ctx.tool_calls] == ["memory.need_context"]
    assert ctx.tool_calls[0].result == {"returned": 5, "degraded": False}
    assert ctx.decision_log == []


def test_broker_reports_degraded_memory_honestly(monkeypatch):
    monkeypatch.setattr(experts_mod, "MemorySearcher", _FakeSearcher)
    _FakeSearcher.package = HydrationPackage(degraded=True, notes="down")
    ctx = _ctx()
    broker = ExpertHandler(registry=registry)._make_context_broker(ctx, [])
    reply = asyncio.run(broker("q"))
    assert "temporarily unavailable" in reply
    assert ctx.tool_calls[0].result["degraded"] is True


def test_broker_reports_no_hits_honestly(monkeypatch):
    monkeypatch.setattr(experts_mod, "MemorySearcher", _FakeSearcher)
    _FakeSearcher.package = HydrationPackage(items=[])
    broker = ExpertHandler(registry=registry)._make_context_broker(_ctx(), [])
    assert "no additional relevant memory" in asyncio.run(broker("q"))
