"""Cooperative cancellation state machine and cancelled SSE reconnect behavior."""

import asyncio

from api import auth, config, sse
from api.run_state import RunState, TERMINAL_STATUSES
from api.run_store import RunStore


def _run(status: str = "orchestrating") -> RunState:
    return RunState(id="run_x", user_id="u1", title="t", brief="b", status=status, session_id="run_x")


def test_cancelled_is_a_terminal_status():
    assert "cancelled" in TERMINAL_STATUSES


def test_cancel_is_noop_on_an_already_terminal_run():
    store = RunStore()
    for status in ("delivered", "blocked", "failed", "cancelled"):
        run = _run(status=status)
        store._runs[run.id] = run
        assert store.request_cancel("u1", run.id) == "noop"
        assert run.status == status  # untouched


def test_cancel_signals_a_live_task():
    async def go():
        store = RunStore()
        run = _run(status="orchestrating")
        run.task = asyncio.ensure_future(asyncio.sleep(10))
        store._runs[run.id] = run

        outcome = store.request_cancel("u1", run.id)
        assert outcome == "cancelling"
        assert run.cancel_requested is True

        with __import__("pytest").raises(asyncio.CancelledError):
            await run.task
        assert run.task.cancelled()

    asyncio.run(go())


def test_cancel_finalizes_directly_after_one_durable_write(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "cancel.db"))
    store = RunStore()
    run = _run(status="orchestrating")  # no .task set (edge: scheduled but not tracked)
    store._runs[run.id] = run

    outcome = store.request_cancel("u1", run.id)

    assert run.status == "cancelled"
    assert outcome == "cancelled"
    assert run.id not in store._runs
    with auth._db() as db:
        rows = db.execute(
            "SELECT status FROM runs WHERE id=? AND user_id=?", (run.id, run.user_id)
        ).fetchall()
    assert [row["status"] for row in rows] == ["cancelled"]
    assert [
        event for event in run.events
        if event.get("type") == "status" and event.get("status") in TERMINAL_STATUSES
    ] == [{"type": "status", "status": "cancelled"}]


def test_direct_cancel_persist_failure_reports_failed_and_retains_live(monkeypatch):
    store = RunStore()
    run = _run(status="orchestrating")
    store._runs[run.id] = run
    calls = 0

    def fail_persist(candidate):
        nonlocal calls
        calls += 1
        assert not any(event.get("type") == "status" for event in candidate.events)
        raise RuntimeError("secret database detail")

    monkeypatch.setattr(store, "persist", fail_persist)

    outcome = store.request_cancel("u1", run.id)

    assert calls == 1
    assert outcome == "failed"
    assert run.status == "failed"
    assert store._runs[run.id] is run
    assert [
        event for event in run.events
        if event.get("type") == "status" and event.get("status") in TERMINAL_STATUSES
    ] == [{"type": "status", "status": "failed"}]
    assert "secret database detail" not in str(run.log)
    assert any("final persistence failed (RuntimeError)" in entry["title"] for entry in run.log)


def test_sse_reconnect_to_cancelled_run_replays_then_closes():
    async def go():
        run = _run(status="cancelled")
        run.emit({"type": "status", "status": "cancelled"})  # buffered terminal event

        frames = []
        # must COMPLETE (not hang on the queue) — the no-report-terminal short-circuit
        async for frame in sse.sse_stream(run):
            frames.append(frame)

        assert any("cancelled" in f for f in frames)

    asyncio.run(asyncio.wait_for(go(), timeout=5))
