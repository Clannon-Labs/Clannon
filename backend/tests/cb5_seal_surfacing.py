"""CB5 "earned seal" surfacing: the output filter's real verdict must reach the
`Run` and the SSE stream on EVERY terminal outcome the filter actually ran for —
both PASS and BLOCK — not just the block path (proposals/to-backend/
2026-07-26_cb5-seal-surfacing-follow-up.md; closes the last unchecked box in
docs/benchmarks/mission/PHASE_3_contract_honesty.md).

Before this fix `ctx.filter_result.groundedness` was computed on every filter
call but read nowhere except inside the blocked branch — a passing turn gave
the user zero signal it was checked at all. Hermetic: pipeline.run faked, DB
helpers patched (same pattern as tests/memory_view_blocked.py).
"""

import asyncio
from types import SimpleNamespace

from api.run_state import RunState
import api.run_driver as rd


def _fake_flow(*, blocked=False, groundedness=None):
    """A finished Flow as run_driver sees it. `groundedness=None` models the
    filter never having run at all (an earlier gate blocked first)."""
    filter_result = (
        None if groundedness is None else SimpleNamespace(groundedness=groundedness)
    )
    ctx = SimpleNamespace(
        blocked=False,
        sanitization_blocked=False,
        verifier_blocked=False,
        filter_blocked=blocked,
        filter_result=filter_result,
        failed=False,
        failure_error=None,
        orchestrator_response=SimpleNamespace(text="the draft answer", message=""),
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


def test_delivered_turn_surfaces_grounded_seal(monkeypatch):
    run = _drive(monkeypatch, _fake_flow(groundedness="grounded"))

    assert run.status == "delivered"
    assert run.verification_state == "grounded"
    assert {"type": "verification", "state": "grounded"} in run.events


def test_delivered_turn_surfaces_partial_seal(monkeypatch):
    run = _drive(monkeypatch, _fake_flow(groundedness="partial"))

    assert run.status == "delivered"
    assert run.verification_state == "partial"


def test_blocked_turn_still_surfaces_its_verdict(monkeypatch):
    # a block IS a verdict — the filter still ran and adjudicated
    run = _drive(monkeypatch, _fake_flow(blocked=True, groundedness="ungrounded"))

    assert run.status == "blocked"
    assert run.block_stage == "filter"
    assert run.verification_state == "ungrounded"


def test_turn_the_filter_never_reached_has_no_seal(monkeypatch):
    # an earlier gate (sanitize/verify) blocked before the filter ever ran —
    # nothing to surface, and no fabricated verdict
    run = _drive(monkeypatch, _fake_flow(groundedness=None))

    assert run.verification_state is None
    assert not any(e.get("type") == "verification" for e in run.events)


def test_verification_state_is_in_full_json():
    run = RunState(id="r1", user_id="u", title="t", brief="b")
    run.on_verification("grounded")
    assert run.full_json()["verificationState"] == "grounded"
