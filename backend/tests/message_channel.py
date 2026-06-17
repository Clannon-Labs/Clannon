"""
The conversational `message` channel: the orchestrator's `say` tool, its mapping to
a live `message_delta` stream (separate from the structured decision log), and the
`message` field on the run shape.
"""

import asyncio
from types import SimpleNamespace

from api.run_state import RunState
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
