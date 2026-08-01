"""An accepted chat answer must ALWAYS reach the user.

The failure this pins was found by the owner using the product, and it is the worst
shape a bug can take: the run reported `delivered`, the answer existed and was
correct, and the user never saw it. The real text was visible only in the server's
terminal log.

Cause: the chat delivery path gated on "did real work happen" —
`if not run.message or ctx.tool_calls or ctx.expert_calls` — so when the model called
`say()` first (setting `run.message`) and then answered directly with no tool or
expert call, every branch was false and the answer was dropped. `say` is a native
tool that does not register in `ctx.tool_calls`, so the guard could not even see the
call that set `run.message`.

The rule now: deliver unless the user has already seen exactly this text.
"""

import asyncio
from types import SimpleNamespace

from api.run_state import RunState
import api.run_driver as rd


def _tool_call(name: str):
    """A tool record shaped the way api/run_sources.py reads it."""
    return SimpleNamespace(tool_name=name, success=True, result={}, sub_tool_calls=[])


def _flow(*, answer: str, presentation: str = "chat", tool_calls=(), expert_calls=()):
    ctx = SimpleNamespace(
        blocked=False,
        sanitization_blocked=False,
        verifier_blocked=False,
        filter_blocked=False,
        filter_result=SimpleNamespace(groundedness="grounded"),
        failed=False,
        failure_error=None,
        orchestrator_response=SimpleNamespace(
            text=answer, message="", presentation=presentation
        ),
        final_response=answer,
        expert_findings=[],
        expert_calls=list(expert_calls),
        tool_calls=list(tool_calls),
    )
    return SimpleNamespace(ctx=ctx)


def _drive(monkeypatch, flow, *, said: str = "") -> RunState:
    async def fake_run(*args, **kwargs):
        return flow

    monkeypatch.setattr(rd.pipeline, "run", fake_run)
    monkeypatch.setattr(rd, "build_model_overrides", lambda *args, **kwargs: {})
    monkeypatch.setattr(rd.STORE, "session_turns", lambda *args, **kwargs: [])
    monkeypatch.setattr(rd.STORE, "persist", lambda run: None)
    run = RunState(id="r1", user_id="u", title="t", brief="b", session_id="r1")
    if said:
        # what a live say() does before the answer is produced
        run.message = said
    asyncio.run(rd.execute(run))
    return run


def _delivered_text(run: RunState) -> str:
    """Everything the user actually received in the chat area."""
    return run.message or ""


def test_answer_reaches_the_user_after_a_say_preamble_with_no_tools(monkeypatch):
    """THE REGRESSION. say() preamble, then a direct answer, no tool or expert call.

    This is exactly the owner's transcript: they asked what model Clannon is, saw
    only "I'm going to answer your question directly", and never got the answer.
    """
    answer = "I'm Clannon, built by Clannon Labs."
    run = _drive(
        monkeypatch,
        _flow(answer=answer),
        said="I'm going to answer your question directly.",
    )
    assert answer in _delivered_text(run), (
        "the accepted answer never reached the chat area — the user saw only the "
        "say() preamble, which is the exact bug this test exists to prevent"
    )


def test_say_preamble_is_kept_alongside_the_answer(monkeypatch):
    """Delivering the answer must not discard what the user already saw."""
    preamble = "Let me answer that directly."
    answer = "I'm Clannon, built by Clannon Labs."
    run = _drive(monkeypatch, _flow(answer=answer), said=preamble)
    delivered = _delivered_text(run)
    assert preamble in delivered and answer in delivered


def test_answer_identical_to_the_say_is_not_duplicated(monkeypatch):
    """The ONE case worth suppressing: the model said exactly the answer already."""
    same = "I'm Clannon, built by Clannon Labs."
    run = _drive(monkeypatch, _flow(answer=same), said=same)
    assert _delivered_text(run).count(same) == 1


def test_answer_reaches_the_user_with_no_say_at_all(monkeypatch):
    """No preamble: the answer is all the user gets, so it had better arrive."""
    answer = "Two plus two is four."
    run = _drive(monkeypatch, _flow(answer=answer))
    assert answer in _delivered_text(run)


def test_answer_still_reaches_the_user_when_tools_did_run(monkeypatch):
    """The old guard's happy path must keep working."""
    answer = "Based on the search, the limit is 1000 req/min."
    run = _drive(
        monkeypatch,
        _flow(answer=answer, tool_calls=[_tool_call("search.web")]),
        said="Looking that up now.",
    )
    assert answer in _delivered_text(run)
