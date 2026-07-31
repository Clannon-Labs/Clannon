"""
Manager context preparation is invisible + prefetched. Agents receive prepared
context but no memory capability or store identity.
"""

import asyncio

from foundation import Flow, HydrationPackage, NormalizedInput, VrakshaContext
from core.memory import manager as _singleton  # the MemoryManager singleton
import core.memory.prefetch as prefetch
import core.orchestrator.loop as loop
from core.orchestrator.ports import Ports
from core.orchestrator.schemas import OrchestratorAnswer


def _norm(text="a real question for the assistant"):
    return NormalizedInput(modality="text", content_type="text/plain", content=text)


def test_prefetch_starts_hydration_in_the_background(monkeypatch):
    async def fake_hydrate(req):
        return HydrationPackage(items=[], notes=None, degraded=False)
    monkeypatch.setattr(_singleton, "hydrate", fake_hydrate)

    async def go():
        flow = Flow.new(_norm(), "s", user_id="u")
        flow.ctx.normalized_input = _norm()
        out = await prefetch.run(flow)
        assert out.ctx.hydration_future is not None     # hydration kicked off, non-blocking
        out = await prefetch.collect(out)
        assert out.ctx.hydration_items == []
    asyncio.run(go())


class _FakeCaps:
    """run_turn fires one normal tool event, then answers."""
    async def run_turn(self, *, output_type, on_event=None, on_message=None, **kw):
        if on_event:
            await on_event({"tool": "search.web", "args": {"query": "y"}})
        return output_type(answer_text="done", presentation="chat", confidence=0.9)


class _FakeLog:
    def __init__(self):
        self.entries = []
    async def emit(self, entry):
        self.entries.append(entry)


def test_prepared_context_is_invisible_in_the_decision_log():
    ports = Ports(caps=_FakeCaps(), log=_FakeLog())
    ctx = VrakshaContext.new(session_id="s", user_id="u", trace_id="t")

    asyncio.run(loop.run_loop(_norm(), ports, ctx))

    kinds = [getattr(e, "kind", "") for e in ports.log.entries]
    tool_calls = [getattr(e, "message", "") for e in ports.log.entries if getattr(e, "kind", "") == "tool_call"]

    assert any("search.web" in m for m in tool_calls)          # a normal tool IS shown
    assert not any("memory" in m for m in tool_calls)
    assert "hydration" not in kinds


class _RecallCaps:
    """run_turn fires a recall tool call carrying a query arg."""
    async def run_turn(self, *, output_type, on_event=None, on_message=None, **kw):
        if on_event:
            await on_event({"tool": "recall", "args": {"query": "the q3 budget"}})
        return output_type(answer_text="done", presentation="chat", confidence=0.9)


def test_recall_event_lifts_query_to_meta_for_clean_rendering():
    # the UI wants meta.tool + meta.query (the wire mapper stringifies nested values, so a
    # query buried in args wouldn't survive cleanly). on_event lifts it to detail's top.
    ports = Ports(caps=_RecallCaps(), log=_FakeLog())
    ctx = VrakshaContext.new(session_id="s", user_id="u", trace_id="t")

    asyncio.run(loop.run_loop(_norm(), ports, ctx))

    recall = [e for e in ports.log.entries
              if getattr(e, "kind", "") == "tool_call" and e.detail.get("tool") == "recall"]
    assert len(recall) == 1
    assert recall[0].detail["tool"] == "recall"             # meta.tool
    assert recall[0].detail["query"] == "the q3 budget"     # meta.query (FE reads this for the quote)
