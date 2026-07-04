"""SSE terminal-event ORDER on the delivered path (the frontend's delivery moment):

    report_delta × N  →  report_done  →  status:delivered

The UI keys the terminal verdict pill on the `status` event and scrolls the
report into view on `report_done` — emitting `status:delivered` first paints a
DELIVERED badge over a still-streaming report (the bug this file pins against;
found via proposals/ 2026-07-04_verify-sse-terminal-order). Contract:
api/README.md `/runs/:id/stream` — "the stream closes after a terminal status".

Hermetic: pipeline.run faked, DB helpers patched (same pattern as
tests/memory_view_blocked.py); events captured via RunState.emit's buffer.
"""

import asyncio
from types import SimpleNamespace

from api.run_state import RunState
import api.run_driver as rd


def _fake_flow(text="word " * 40):
    ctx = SimpleNamespace(
        blocked=False,
        sanitization_blocked=False,
        verifier_blocked=False,
        filter_blocked=False,
        failed=False,
        failure_error=None,
        orchestrator_response=SimpleNamespace(text=text, message=""),
        final_response=text,
        memory_writes_requested=[],
        memory_writes_persisted=[],   # what the Manager actually wrote (surfaced on delivery)
        expert_findings=[],
        expert_calls=[],
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


def test_delivered_terminal_order_report_before_status(monkeypatch):
    run = _drive(monkeypatch, _fake_flow())
    types = [e.get("type") for e in run.events]

    assert "report_delta" in types and "report_done" in types
    done_at = types.index("report_done")
    delivered_at = next(
        i for i, e in enumerate(run.events)
        if e.get("type") == "status" and e.get("status") == "delivered"
    )
    # every report_delta precedes report_done, which strictly precedes the
    # terminal status — the DELIVERED badge can never predate the report
    assert max(i for i, t in enumerate(types) if t == "report_delta") < done_at
    assert done_at < delivered_at, (
        f"status:delivered (idx {delivered_at}) must come AFTER report_done (idx {done_at})"
    )
    # and no status:delivered sneaks in anywhere before report_done
    assert not any(
        e.get("type") == "status" and e.get("status") == "delivered"
        for e in run.events[:done_at]
    )


def test_delivered_run_has_report_when_status_flips(monkeypatch):
    # the sse.py reconnect guard's premise: by the time status is terminal-delivered,
    # run.report is set — a live delivered-but-report-None window can't occur
    run = _drive(monkeypatch, _fake_flow())
    assert run.status == "delivered" and run.report is not None
