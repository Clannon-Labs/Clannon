"""Tests for the Vraksha-owned orchestrator reasoning loop."""

import asyncio

from foundation import MaxRetriesExceededError, NormalizedInput, VrakshaContext, constants
from core.orchestrator import loop as loop_mod
from core.orchestrator.schemas import ExpertRequest, OrchestratorDecision, ToolRequest
from core.orchestrator.utils.wiring import build_default_ports


def _norm():
    return NormalizedInput(modality="text", content_type="text/plain", content="hi")


def _run():
    ctx = VrakshaContext.new("s")
    ports = build_default_ports(ctx)
    resp = asyncio.run(loop_mod.run_loop(_norm(), ports, ctx))
    return resp, ctx


def test_direct_answer(monkeypatch):
    async def decide(normalized, hydration, obs, turn, *, force_answer=False):
        return OrchestratorDecision(kind="answer", answer_text="done", confidence=0.9)
    monkeypatch.setattr(loop_mod.advisor, "decide", decide)

    resp, ctx = _run()
    assert resp.text == "done"
    assert any(e.kind == "answer" for e in ctx.decision_log)


def test_tool_then_answer(monkeypatch):
    calls = {"n": 0}

    async def decide(normalized, hydration, obs, turn, *, force_answer=False):
        calls["n"] += 1
        if calls["n"] == 1:
            return OrchestratorDecision(kind="call_tool", tool=ToolRequest(name="search"))
        return OrchestratorDecision(kind="answer", answer_text="ok")
    monkeypatch.setattr(loop_mod.advisor, "decide", decide)

    resp, ctx = _run()
    assert resp.text == "ok"
    assert len(ctx.tool_calls) == 1 and ctx.tool_calls[0].tool_name == "search"


def test_experts_then_answer_orchestrator_sees_only_summaries(monkeypatch):
    calls = {"n": 0}

    async def decide(normalized, hydration, obs, turn, *, force_answer=False):
        calls["n"] += 1
        if calls["n"] == 1:
            return OrchestratorDecision(
                kind="spawn_experts",
                experts=[ExpertRequest(name="research", task="t")],
            )
        # On the next turn the loop must have fed back summaries, not raw findings.
        assert any(getattr(o, "summary", None) for o in obs)
        return OrchestratorDecision(kind="answer", answer_text="synthesized")
    monkeypatch.setattr(loop_mod.advisor, "decide", decide)

    resp, ctx = _run()
    assert resp.text == "synthesized"
    assert len(ctx.expert_findings) == 1
    assert resp.finding_refs == [ctx.expert_findings[0].ref]


def test_turn_cap_forces_a_final_answer(monkeypatch):
    monkeypatch.setattr(constants, "ORCHESTRATOR_MAX_TURNS", 2)

    async def decide(normalized, hydration, obs, turn, *, force_answer=False):
        if force_answer:
            return OrchestratorDecision(kind="answer", answer_text="forced")
        return OrchestratorDecision(kind="need_more")
    monkeypatch.setattr(loop_mod.advisor, "decide", decide)

    resp, _ = _run()
    assert resp.text == "forced"


def test_turn_cap_without_answer_fails_closed(monkeypatch):
    monkeypatch.setattr(constants, "ORCHESTRATOR_MAX_TURNS", 2)

    async def decide(normalized, hydration, obs, turn, *, force_answer=False):
        return OrchestratorDecision(kind="need_more")
    monkeypatch.setattr(loop_mod.advisor, "decide", decide)

    try:
        _run()
        assert False, "should fail closed at the turn cap"
    except MaxRetriesExceededError:
        pass
