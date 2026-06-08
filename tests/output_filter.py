"""Tests for the output filter stage (security/filter)."""

import asyncio

from foundation import Flow, NormalizedInput, OrchestratorResponse
import security.filter.filter as filter_stage
from security.filter.schemas import FilterResult


def _flow(text="hello"):
    flow = Flow.new(NormalizedInput(modality="text", content_type="text/plain", content="q"), "s")
    flow.ctx.orchestrator_response = OrchestratorResponse(text=text, confidence=0.9)
    return flow


def test_filter_proceeds(monkeypatch):
    async def fake(response, findings):
        return FilterResult(proceed=True)
    monkeypatch.setattr(filter_stage, "_filter", fake)

    out = asyncio.run(filter_stage.run(_flow()))
    assert out.status.value == "ok"
    assert out.ctx.filter_result.proceed is True


def test_filter_blocks_unsafe(monkeypatch):
    async def fake(response, findings):
        return FilterResult(proceed=False, blocked=True, reason="policy")
    monkeypatch.setattr(filter_stage, "_filter", fake)

    out = asyncio.run(filter_stage.run(_flow()))
    assert out.status.value == "blocked"
    assert out.ctx.filter_blocked is True
