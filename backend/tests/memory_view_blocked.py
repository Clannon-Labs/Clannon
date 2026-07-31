"""Run rows never shadow Manager-owned memory."""

import asyncio
from types import SimpleNamespace

from api.run_state import RunState
import api.run_driver as rd


def _fake_flow(*, blocked=False, failed=False):
    ctx = SimpleNamespace(
        blocked=blocked,
        sanitization_blocked=False,
        verifier_blocked=False,
        filter_blocked=blocked,
        filter_result=SimpleNamespace(
            groundedness="ungrounded" if blocked else "grounded"
        ),
        failed=failed,
        failure_error=None,
        orchestrator_response=SimpleNamespace(text="the draft answer", message=""),
        final_response="the draft answer",
        expert_findings=[],
        expert_calls=[],
        tool_calls=[],
    )
    return SimpleNamespace(ctx=ctx)


def _drive(monkeypatch, flow) -> RunState:
    async def fake_run(*args, **kwargs):
        return flow

    monkeypatch.setattr(rd.pipeline, "run", fake_run)
    monkeypatch.setattr(rd, "build_model_overrides", lambda *args, **kwargs: {})
    monkeypatch.setattr(rd.STORE, "session_turns", lambda *args, **kwargs: [])
    monkeypatch.setattr(rd.STORE, "persist", lambda run: None)
    run = RunState(id="r1", user_id="u", title="t", brief="b", session_id="r1")
    asyncio.run(rd.execute(run))
    return run


def test_blocked_turn_has_no_run_shadow_memory(monkeypatch):
    run = _drive(monkeypatch, _fake_flow(blocked=True))
    assert run.status == "blocked"
    assert run.memory_writes == []


def test_delivered_turn_also_has_no_run_shadow_memory(monkeypatch):
    run = _drive(monkeypatch, _fake_flow())
    assert run.status == "delivered"
    assert run.memory_writes == []
