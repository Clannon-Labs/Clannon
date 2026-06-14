"""Tests for the simple orchestrator ports: memory door + decision-log sink.

The memory tests run against the real manager (Qdrant + embeddings, per
core/memory/ARCHITECTURE.md) and skip when Qdrant isn't reachable. Memory is
scoped by user_id — session_id is provenance, not a recall boundary.
"""

import asyncio
import os
import urllib.request
import uuid

import pytest

from foundation import (
    HydrationRequest,
    MemoryStore,
    MemoryWriteProposal,
    NormalizedInput,
    VrakshaContext,
)
from core.memory import MemoryManager
from core.orchestrator.schemas import DecisionLogEntry
from core.orchestrator.utils.decision_log import CtxDecisionLog


def _qdrant_up() -> bool:
    try:
        urllib.request.urlopen(
            os.getenv("QDRANT_URL", "http://localhost:6333") + "/readyz", timeout=2
        )
        return True
    except Exception:
        return False


_needs_qdrant = pytest.mark.skipif(not _qdrant_up(), reason="qdrant not reachable")


def _norm(text: str) -> NormalizedInput:
    return NormalizedInput(modality="text", content_type="text/plain", content=text)


@_needs_qdrant
def test_memory_store_and_recall_for_user():
    manager = MemoryManager()
    user = f"test-{uuid.uuid4().hex[:8]}"

    async def go():
        before = await manager.hydrate(
            HydrationRequest(session_id="s", user_id=user, normalized=_norm("project codename"))
        )
        assert before.items == [] and before.notes
        await manager.record_write_proposals(
            user, "s",
            [MemoryWriteProposal(store=MemoryStore.EPISODIC, content="the project codename is BLUEFERN")],
        )
        after = await manager.hydrate(
            HydrationRequest(session_id="s", user_id=user, normalized=_norm("what is the project codename?"))
        )
        await manager.delete_user(user)
        return after

    after = asyncio.run(go())
    assert any("BLUEFERN" in item.content for item in after.items)


@_needs_qdrant
def test_memory_is_scoped_by_user():
    manager = MemoryManager()
    writer, other = (f"test-{uuid.uuid4().hex[:8]}" for _ in range(2))

    async def go():
        await manager.record_write_proposals(
            writer, "s1",
            [MemoryWriteProposal(store=MemoryStore.EPISODIC, content="private fact: the kiwi code")],
        )
        package = await manager.hydrate(
            HydrationRequest(session_id="s1", user_id=other, normalized=_norm("the kiwi code private fact"))
        )
        await manager.delete_user(writer)
        return package

    # same session id, different user — nothing leaks across the user filter
    assert asyncio.run(go()).items == []


def test_decision_log_sink_appends_to_ctx():
    ctx = VrakshaContext.new("s")
    sink = CtxDecisionLog(ctx)

    async def go():
        await sink.emit(DecisionLogEntry(kind="answer", message="a"))
        await sink.emit(DecisionLogEntry(kind="observation", message="b"))

    asyncio.run(go())
    assert [e.message for e in ctx.decision_log] == ["a", "b"]
