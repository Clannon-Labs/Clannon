"""Tests for the simple orchestrator ports: memory door + decision-log sink."""

import asyncio

from foundation import (
    HydrationRequest,
    MemoryStore,
    MemoryWriteProposal,
    VrakshaContext,
)
from core.memory import MemoryManager
from core.orchestrator.schemas import DecisionLogEntry
from core.orchestrator.utils.decision_log import CtxDecisionLog


def test_memory_store_and_recall_within_session():
    manager = MemoryManager()

    async def go():
        before = await manager.hydrate(HydrationRequest(session_id="s"))
        assert before.items == [] and before.notes
        await manager.record_write_proposals(
            "s", [MemoryWriteProposal(store=MemoryStore.EPISODIC, content="x")]
        )
        return await manager.hydrate(HydrationRequest(session_id="s"))

    after = asyncio.run(go())
    assert len(after.items) == 1 and after.items[0].content == "x"


def test_memory_is_scoped_by_session():
    manager = MemoryManager()

    async def go():
        await manager.record_write_proposals(
            "s1", [MemoryWriteProposal(store=MemoryStore.EPISODIC, content="a")]
        )
        return await manager.hydrate(HydrationRequest(session_id="s2"))

    assert asyncio.run(go()).items == []


def test_decision_log_sink_appends_to_ctx():
    ctx = VrakshaContext.new("s")
    sink = CtxDecisionLog(ctx)

    async def go():
        await sink.emit(DecisionLogEntry(kind="answer", message="a"))
        await sink.emit(DecisionLogEntry(kind="observation", message="b"))

    asyncio.run(go())
    assert [e.message for e in ctx.decision_log] == ["a", "b"]
