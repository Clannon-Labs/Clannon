"""Tests for the orchestrator Flow stage (entry point)."""

import asyncio

from foundation import Flow, NormalizedInput, Origin, constants
from core.orchestrator import loop as loop_mod
from core.orchestrator import orchestrator as stage
from core.orchestrator.schemas import OrchestratorDecision


def _flow():
    return Flow.new(NormalizedInput(modality="text", content_type="text/plain", content="hi"), "s")


def test_stage_happy_path_sets_response_and_journals_origin(monkeypatch):
    async def decide(normalized, hydration, obs, turn, *, force_answer=False):
        return OrchestratorDecision(kind="answer", answer_text="hi there", confidence=0.8)
    monkeypatch.setattr(loop_mod.advisor, "decide", decide)

    out = asyncio.run(stage.run(_flow()))
    assert out.status.value == "ok"
    assert out.ctx.orchestrator_response.text == "hi there"
    assert any(e.origin == Origin.ORCHESTRATOR for e in out.journal)


def test_stage_fails_closed_on_advisor_error(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("advisor broke")
    monkeypatch.setattr(loop_mod.advisor, "decide", boom)

    out = asyncio.run(stage.run(_flow()))
    assert out.status.value == "error"


def test_stage_times_out_and_fails(monkeypatch):
    monkeypatch.setattr(constants, "ORCHESTRATOR_TIMEOUT_S", 0.01)

    async def slow(*args, **kwargs):
        await asyncio.sleep(0.1)
        return OrchestratorDecision(kind="answer", answer_text="late")
    monkeypatch.setattr(loop_mod.advisor, "decide", slow)

    out = asyncio.run(stage.run(_flow()))
    assert out.status.value == "error"
