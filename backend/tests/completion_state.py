"""Honest completion: a run that DEGRADED must not read as a clean success.

When the reasoning loop cannot finish (wall-clock timeout, provider rate-limit
storm, unexpected fault) the orchestrator does not fail the run — it answers from
whatever it already gathered (`core/orchestrator/utils/recovery.py`). That answer
is real and it is delivered, so `status` stays `delivered` and the filter can
honestly call it grounded.

The consequence, reported from a real browser run (`run_16cac313852a`, frontend
proposal 2026-07-28): the UI showed **DELIVERED** beside a report whose first line
was "This run couldn't finish in the time allowed." The frontend had no structured
way to tell success from timeout-with-partial-result short of parsing report prose.

`completion_state` is that third axis. It is set from the orchestrator's OWN
degraded metadata — never inferred from the report text, never guessed.

Hermetic: pipeline.run faked, DB helpers patched (same pattern as
tests/cb5_seal_surfacing.py).
"""

import asyncio
from types import SimpleNamespace

import pytest

from api.run_state import RunState
import api.run_driver as rd


def _fake_flow(*, metadata=None):
    """A finished Flow as run_driver sees it. `metadata` is what the orchestrator
    attached to its response — `{"degraded": True, "cause": ...}` on the degraded
    path, and a plain dict (or nothing) on a healthy turn."""
    ctx = SimpleNamespace(
        blocked=False,
        sanitization_blocked=False,
        verifier_blocked=False,
        filter_blocked=False,
        filter_result=SimpleNamespace(groundedness="grounded"),
        failed=False,
        failure_error=None,
        orchestrator_response=SimpleNamespace(
            text="the draft answer", message="", metadata=metadata or {}
        ),
        final_response="the draft answer",
        memory_writes_requested=[],
        memory_writes_persisted=[],
        expert_findings=[],
        expert_calls=[],
        tool_calls=[],
    )
    return SimpleNamespace(ctx=ctx)


def _drive(monkeypatch, flow) -> RunState:
    async def fake_run(*a, **k):
        return flow
    monkeypatch.setattr(rd.pipeline, "run", fake_run)
    monkeypatch.setattr(rd, "build_model_overrides", lambda *a, **k: {})
    monkeypatch.setattr(rd.STORE, "session_turns", lambda *a, **k: [])
    monkeypatch.setattr(rd.STORE, "persist", lambda run: None)

    run = RunState(id="r1", user_id="u", title="t", brief="b", session_id="r1")
    asyncio.run(rd.execute(run))
    return run


def test_healthy_run_is_complete(monkeypatch):
    run = _drive(monkeypatch, _fake_flow())

    assert run.status == "delivered"
    assert run.completion_state == "complete"
    assert run.completion_reason is None


@pytest.mark.parametrize("cause", ["timeout", "rate_limit", "error"])
def test_degraded_run_is_partial_and_says_why(monkeypatch, cause):
    """Every FailureKind recovery.py can produce must survive to the API. A cause
    the UI cannot name is barely better than no signal at all."""
    run = _drive(monkeypatch, _fake_flow(metadata={"degraded": True, "cause": cause}))

    # the answer really was delivered — degrading is not failing
    assert run.status == "delivered"
    # ...but it did not finish the work, and now says so
    assert run.completion_state == "partial"
    assert run.completion_reason == cause


def test_degraded_run_still_earns_its_seal(monkeypatch):
    """completion_state is a SEPARATE axis from verification_state. A degraded
    answer built from real findings is still grounded; collapsing the two would
    reintroduce the same dishonesty in a different field."""
    run = _drive(monkeypatch, _fake_flow(metadata={"degraded": True, "cause": "timeout"}))

    assert run.verification_state == "grounded"
    assert run.completion_state == "partial"


def test_response_without_metadata_is_not_treated_as_degraded(monkeypatch):
    """Absence of the marker must read as complete, not as unknown-so-assume-bad.
    Guards the getattr fallback for any response shape lacking `metadata`."""
    flow = _fake_flow()
    flow.ctx.orchestrator_response = SimpleNamespace(text="answer", message="")

    run = _drive(monkeypatch, flow)

    assert run.completion_state == "complete"
    assert run.completion_reason is None


def test_completion_fields_are_in_full_json():
    run = RunState(id="r1", user_id="u", title="t", brief="b")
    assert run.full_json()["completionState"] == "complete"
    assert run.full_json()["completionReason"] is None

    run.completion_state = "partial"
    run.completion_reason = "timeout"
    assert run.full_json()["completionState"] == "partial"
    assert run.full_json()["completionReason"] == "timeout"
