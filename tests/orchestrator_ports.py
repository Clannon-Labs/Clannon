"""Tests for the orchestrator's Phase-1 ports (stubs + sink + router)."""

import asyncio

from foundation import (
    HydrationRequest,
    MemoryStore,
    MemoryWriteProposal,
    NormalizedInput,
    VrakshaContext,
)
from core.memory import MemoryManager
from core.orchestrator.experts import StubExpertHandler
from core.orchestrator.tools import StubToolHandler
from core.orchestrator.schemas import DecisionLogEntry, ExpertRequest, ToolRequest
from core.orchestrator.utils.decision_log import QueueDecisionLogSink
from core.orchestrator.utils.router import DefaultExpertRouter


def _ctx():
    return VrakshaContext.new("s")


def test_memory_manager_stub_hydration_and_proposals():
    m = MemoryManager()
    pkg = asyncio.run(m.hydrate(HydrationRequest(session_id="s")))
    assert pkg.items == []
    asyncio.run(m.record_write_proposals([MemoryWriteProposal(store=MemoryStore.EPISODIC, content="x")]))
    assert len(m.recorded_proposals) == 1


def test_default_router_returns_no_experts():
    router = DefaultExpertRouter()
    norm = NormalizedInput(modality="text", content_type="text/plain", content="hi")
    assert router.route(norm, []) == []


def test_stub_expert_handler_honors_two_output_split():
    ctx = _ctx()
    handler = StubExpertHandler()
    summaries = asyncio.run(handler.run_experts([ExpertRequest(name="research", task="t")], ctx))

    assert len(summaries) == 1 and summaries[0].expert == "research"
    # Full findings are buffered separately; the orchestrator only gets the summary.
    assert len(ctx.expert_findings) == 1
    assert ctx.expert_findings[0].ref == summaries[0].finding_ref
    assert len(ctx.expert_calls) == 1 and ctx.expert_calls[0].success is True


def test_stub_tool_handler_records_failed_call():
    ctx = _ctx()
    record = asyncio.run(StubToolHandler().call_tool(ToolRequest(name="search", arguments={"q": "x"}), ctx))
    assert record.tool_name == "search" and record.success is False
    assert len(ctx.tool_calls) == 1


def test_decision_log_sink_streams_and_mirrors_to_ctx():
    ctx = _ctx()
    sink = QueueDecisionLogSink(ctx)

    async def go():
        await sink.emit(DecisionLogEntry(kind="answer", message="a"))
        await sink.emit(DecisionLogEntry(kind="observation", message="b"))
        await sink.close()
        return [e async for e in sink.stream()]

    got = asyncio.run(go())
    assert [e.message for e in got] == ["a", "b"]
    assert [e.seq for e in got] == [0, 1]          # monotonic ordering
    assert len(ctx.decision_log) == 2              # mirrored for audit
