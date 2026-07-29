"""
The conversational `message` channel: the orchestrator's `say` tool, its mapping to
a live `message_delta` stream (separate from the structured decision log), and the
`message` field on the run shape.
"""

import asyncio
from types import SimpleNamespace

import pytest

from foundation import (
    ExpertCallRecord,
    OrchestratorResponse,
    ToolCallRecord,
    VrakshaContext,
)
from api.run_state import RunState
import api.run_driver as rd
from registry.capabilities.handler.support import build_orchestrator_tools


def test_say_tool_present_only_when_a_message_sink_is_wired():
    async def on_message(text):
        pass

    with_sink = build_orchestrator_tools([], [], on_message=on_message)
    without = build_orchestrator_tools([], [])
    assert any(getattr(t, "__name__", "") == "say" for t in with_sink)
    assert not any(getattr(t, "__name__", "") == "say" for t in without)


def test_say_tool_streams_through_on_message():
    captured = []

    async def on_message(text):
        captured.append(text)

    say = next(t for t in build_orchestrator_tools([], [], on_message=on_message)
               if getattr(t, "__name__", "") == "say")
    result = asyncio.run(say("Three specialists are digging in — back shortly."))
    assert captured == ["Three specialists are digging in — back shortly."]
    assert "user" in result.lower()


def test_message_kind_maps_to_message_delta_not_the_decision_log():
    run = RunState(id="m1", user_id="u1", title="t", brief="b", session_id="m1")
    run.on_log_entry(SimpleNamespace(kind="message", message="Hello ", detail={}))
    run.on_log_entry(SimpleNamespace(kind="message", message="there.", detail={}))
    run.on_log_entry(SimpleNamespace(kind="tool_call", message="calling search.web", detail={}))

    deltas = [e["text"] for e in run.events if e.get("type") == "message_delta"]
    assert deltas == ["Hello ", "there."]
    assert run.message == "Hello there."            # accumulated chat bubble
    # the message channel is SEPARATE from the structured decision log
    assert len(run.log) == 1 and run.log[0]["title"] == "calling search.web"


def test_message_is_in_the_run_shape_alongside_report():
    run = RunState(id="m2", user_id="u1", title="t", brief="b", session_id="m2")
    run.message = "Here's a quick note on what I did."
    run.report = "# The deliverable"
    j = run.full_json()
    assert j["message"] == "Here's a quick note on what I did."
    assert j["report"] == "# The deliverable"


def _chat_ctx(*, filtered: str = "Filtered final answer.") -> VrakshaContext:
    ctx = VrakshaContext.new("chat", user_id="u1")
    ctx.orchestrator_response = OrchestratorResponse(
        text="Unfiltered orchestrator draft.",
        presentation="chat",
    )
    ctx.final_response = filtered
    return ctx


def _drive_chat(monkeypatch, ctx: VrakshaContext, *, say: str = "") -> RunState:
    persisted: list[tuple[str | None, str | None]] = []

    async def fake_run(*args, **kwargs):
        if say:
            kwargs["decision_log"].append(
                SimpleNamespace(kind="message", message=say, detail={})
            )
        return SimpleNamespace(ctx=ctx)

    monkeypatch.setattr(rd.pipeline, "run", fake_run)
    monkeypatch.setattr(rd, "build_model_overrides", lambda *a, **k: {})
    monkeypatch.setattr(rd.STORE, "session_turns", lambda *a, **k: [])
    monkeypatch.setattr(
        rd.STORE,
        "persist",
        lambda candidate: persisted.append((candidate.message, candidate.report)),
    )
    monkeypatch.setattr(rd._decision_audit, "write_decision_records", lambda **k: None)

    run = RunState(id="chat-run", user_id="u1", title="t", brief="b", session_id="chat-run")
    asyncio.run(rd.execute(run))
    assert persisted == [(run.message, run.report)]
    return run


def _message_deltas(run: RunState) -> list[str]:
    return [e["text"] for e in run.events if e.get("type") == "message_delta"]


def _assert_no_report_events(run: RunState) -> None:
    assert run.report is None
    assert not any(e.get("type") in {"report_delta", "report_done"} for e in run.events)


def test_chat_without_say_delivers_only_filtered_final_message(monkeypatch):
    ctx = _chat_ctx(filtered="Accepted, filtered chat.")
    ctx.expert_findings.append(
        SimpleNamespace(metadata={"artifacts": [{"id": "artifact-1", "name": "result.csv"}]})
    )

    run = _drive_chat(monkeypatch, ctx)

    assert run.message == "Accepted, filtered chat."
    assert _message_deltas(run) == ["Accepted, filtered chat."]
    assert run.artifacts == [{"id": "artifact-1", "name": "result.csv"}]
    _assert_no_report_events(run)


def test_chat_with_only_accidental_say_retains_say_as_sole_response(monkeypatch):
    run = _drive_chat(
        monkeypatch,
        _chat_ctx(filtered="Weak model repeated this answer."),
        say="Casual answer already shown.",
    )

    assert run.message == "Casual answer already shown."
    assert _message_deltas(run) == ["Casual answer already shown."]
    _assert_no_report_events(run)


@pytest.mark.parametrize("work_kind", ["tool", "expert"])
def test_substantive_chat_appends_filtered_final_after_say(monkeypatch, work_kind):
    ctx = _chat_ctx(filtered="Accepted answer after the work.")
    if work_kind == "tool":
        ctx.tool_calls.append(
            ToolCallRecord(
                tool_name="calculator.eval",
                arguments={"expr": "2+2"},
                result={"value": 4},
                success=True,
            )
        )
    else:
        ctx.expert_calls.append(
            ExpertCallRecord(
                expert_name="analysis",
                arguments={"prompt": "check the result"},
                result={"summary": "checked"},
                success=True,
            )
        )

    run = _drive_chat(monkeypatch, ctx, say="I’m checking that now.")

    assert run.message == "I’m checking that now.\n\nAccepted answer after the work."
    assert _message_deltas(run) == [
        "I’m checking that now.",
        "\n\nAccepted answer after the work.",
    ]
    _assert_no_report_events(run)
