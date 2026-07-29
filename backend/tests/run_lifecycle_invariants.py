"""
Run-lifecycle concurrency invariants (API & Runtime specialist audit, 2026-07-26).

Targets the races the route layer's comments *claim* can't happen, and pins the
ones that are actually correct today so a future edit can't quietly break them.
Hermetic: no live server, no real pipeline, no paid keys — same fake-flow /
monkeypatch conventions as tests/sse_terminal_order.py and
tests/sse_failure_terminal.py.

Findings this file backs (see reports/api/ for the write-up):

1. Run creation registers `execute()` immediately after exposing the run through
   `RunStore`, before uploaded-file persistence can suspend. The parametrized
   cancellation test uses a genuinely asynchronous artifact store and proves
   both root and follow-up routes retain a cancellable task, finish once as
   `cancelled`, and never enter paid pipeline work.
2. Server shutdown (app.py's lifespan shutdown loop) routes through the SAME
   `RunStore.request_cancel` as a user's `POST /runs/:id/cancel` — deliberately:
   an in-flight run at process exit is honestly finalized as `cancelled` and
   persisted, not left dangling for the next boot to resurrect.
   `test_shutdown_drain_finalizes_inflight_run_as_cancelled` pins this end to
   end through the real `lifespan` context manager. `run_driver.py`'s
   `CancelledError` handler comment previously implied shutdown should NOT be
   treated as a stop — corrected; `cancel_requested` distinguishes "a stop THIS
   server signalled" (user cancel OR shutdown) from any other CancelledError
   source, not "user vs. shutdown".
3. Delete-mid-flight (`RunStore.delete_session`) does NOT set `cancel_requested`
   — confirmed correct: `execute()`'s `except CancelledError` re-raises (a
   delete is not a user cancel), and the `finally` still skips `persist()`
   because `run.deleted` is set. Pinned so it stays this way.
4. `run_usage.total_tokens`, read in the `except` handlers after the `with
   usage_scope(): ...` block has unwound, stays valid — `usage_scope`'s
   context manager only resets a ContextVar; it never mutates the `Usage`
   object callers hold a reference to. Pinned.
5. SSE subscriber queues are removed from `run.subscribers` on every
   disconnect, live or not — no leak across repeated connect/cancel cycles.
6. A reconnect to a run that has ALREADY been persisted (evicted from the
   in-memory store) replays zero buffered frames and closes immediately —
   `events` is deliberately runtime-only (tests/run_state_roundtrip.py), so
   `_from_row` never repopulates it. `api/README.md` previously read as if
   every reconnect replays the buffered sequence regardless; corrected there
   to say this only holds for a still-live run, and a client revisiting a
   finished run must fetch `GET /runs/:id` for content instead. Confirmed this
   is docs-only, not a live gap: frontend/src/lib/api/hooks.ts's `useLiveRun`
   never opens the SSE stream at all once `run.status` (from the REST query)
   is terminal, so a reconnect to a finished run already renders from
   `GET /runs/:id` in practice.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from api.run_state import RunState
from api.run_store import RunStore
from api import sse
import api.run_driver as run_driver
import api.run_inputs as run_inputs


# ── shared fixtures ───────────────────────────────────────────────────────────


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """A RunStore backed by a throwaway SQLite file, wired into every module that
    imported STORE by name (run_driver, and api.runs — the façade app.py's
    lifespan shutdown loop reads via `runs.STORE`) — patching api.run_store.STORE
    alone would miss both."""
    from api import config, run_store
    import api.runs as runs_mod

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "lifecycle.db"))
    fresh = RunStore()
    monkeypatch.setattr(run_store, "STORE", fresh)
    monkeypatch.setattr(runs_mod, "STORE", fresh)
    monkeypatch.setattr(run_driver, "STORE", fresh)
    return fresh


def _fake_flow(text: str = "delivered text"):
    """Minimal fake Flow — enough for execute()'s delivered branch. Any ctx
    attribute execute() reads inside the best-effort try/excepts (decision-log
    mirroring) that ISN'T set here is fine: those blocks swallow AttributeError
    by design (same fixture shape as tests/sse_terminal_order.py)."""
    ctx = SimpleNamespace(
        blocked=False,
        sanitization_blocked=False,
        verifier_blocked=False,
        filter_blocked=False,
        filter_result=None,
        failed=False,
        failure_error=None,
        orchestrator_response=SimpleNamespace(text=text, message=""),
        final_response=text,
        memory_writes_persisted=[],
        expert_findings=[],
        expert_calls=[],
        tool_calls=[],
    )
    return SimpleNamespace(ctx=ctx)


@pytest.fixture()
def hermetic_execute(monkeypatch):
    """Patches everything execute() touches besides the pipeline call and the
    store's persistence path, so the real execute()/persist() are under test."""
    monkeypatch.setattr(run_driver, "build_model_overrides", lambda *a, **k: {})
    monkeypatch.setattr(run_driver.auth, "fetch_wiki", lambda *a, **k: [])

    def _patch_pipeline(flow):
        async def fake_run(*a, **k):
            return flow
        monkeypatch.setattr(run_driver.pipeline, "run", fake_run)

    return _patch_pipeline


# ── (1) cancel vs. task registration ─────────────────────────────────────────


class _SuspendingArtifactStore:
    """Stands in for a genuinely-async artifact backend (S3, aiofiles, a DB
    write) — unlike the real LocalArtifactStore, its `put` actually yields to
    the event loop, opening the window app.py's comment claims can't exist."""

    def __init__(self, reached: asyncio.Event, release: asyncio.Event) -> None:
        self._reached = reached
        self._release = release

    async def put(self, ns: str, name: str, data: bytes):
        self._reached.set()
        await self._release.wait()
        return SimpleNamespace(id=f"{ns}/{name}")


def _make_root(store: RunStore) -> RunState:
    return store.create("u1", "test brief")


# a synthetic parent, read-only from create_followup's point of view (it only
# reads .id/.session_id/.project_id) — it never needs to exist in `store` itself
_PARENT = RunState(
    id="run_parent0", user_id="u1", title="parent", brief="parent brief", session_id="run_parent0"
)


def _make_followup(store: RunStore) -> RunState:
    return store.create_followup("u1", "followup ask", _PARENT)


async def _simulate_create_run(store: RunStore, input_files: list, make_run=_make_root) -> RunState:
    """Mirror both routes: expose run, then register execute() without awaiting."""
    run = make_run(store)
    run.task = asyncio.ensure_future(run_driver.execute(run, input_files))
    return run


@pytest.mark.parametrize("make_run", [_make_root, _make_followup], ids=["create_run", "follow_up_run"])
def test_cancel_during_async_input_persistence_stops_registered_task(
    store, monkeypatch, make_run
):
    """A suspending artifact backend cannot reopen the registration race.

    Cancellation sees the already-registered execute() task, interrupts input
    persistence before pipeline work, and produces one durable cancelled result.
    """
    pipeline_called = False

    async def fake_pipeline(*a, **k):
        nonlocal pipeline_called
        pipeline_called = True
        return _fake_flow()

    monkeypatch.setattr(run_driver.pipeline, "run", fake_pipeline)
    monkeypatch.setattr(run_driver, "build_model_overrides", lambda *a, **k: {})
    monkeypatch.setattr(run_driver.auth, "fetch_wiki", lambda *a, **k: [])
    reached = asyncio.Event()
    release = asyncio.Event()
    monkeypatch.setattr(
        run_inputs, "LocalArtifactStore", lambda: _SuspendingArtifactStore(reached, release)
    )
    input_file = SimpleNamespace(name="f.txt", data=b"hi", as_dict=lambda: {"name": "f.txt"})

    async def go():
        run = await _simulate_create_run(store, [input_file], make_run)
        await asyncio.wait_for(reached.wait(), timeout=2)

        assert run.task is not None and not run.task.done()
        assert store.request_cancel("u1", run.id) == "cancelling"
        await run.task
        return run.id

    rid = asyncio.run(asyncio.wait_for(go(), timeout=5))
    assert pipeline_called is False
    assert store.get("u1", rid).status == "cancelled"


def test_shutdown_drain_finalizes_inflight_run_as_cancelled(store, monkeypatch):
    """app.py's lifespan shutdown loop calls the SAME `RunStore.request_cancel`
    as `POST /runs/:id/cancel` (app.py:78) — so it also sets `cancel_requested`,
    and execute()'s `except CancelledError` honors it exactly like a user stop:
    the run persists as `cancelled`, not left dangling for the next boot to
    resurrect. This is deliberate (see the corrected comment in run_driver.py's
    CancelledError handler) — pin it end to end through the real `lifespan`
    context manager, not just the flag."""
    import core.warmup as wm
    import api.app as app_mod

    monkeypatch.setattr(wm, "warmup", lambda: asyncio.sleep(0))

    async def never_returns(*a, **k):
        await asyncio.sleep(60)

    monkeypatch.setattr(run_driver.pipeline, "run", never_returns)
    monkeypatch.setattr(run_driver, "build_model_overrides", lambda *a, **k: {})
    monkeypatch.setattr(run_driver.auth, "fetch_wiki", lambda *a, **k: [])

    async def go():
        run = store.create("u1", "brief")
        run.task = asyncio.ensure_future(run_driver.execute(run, []))
        await asyncio.sleep(0)  # let it reach the await inside pipeline.run

        async with app_mod.lifespan(app_mod.app):
            pass  # immediate startup + shutdown; shutdown drains this run's task

        assert run.task.done() and not run.task.cancelled(), (
            "execute() must swallow the shutdown-initiated CancelledError and "
            "complete normally, not propagate it as a bare task cancellation"
        )
        assert run.status == "cancelled"
        return run.id

    rid = asyncio.run(asyncio.wait_for(go(), timeout=15))
    assert store.get("u1", rid).status == "cancelled"


# ── (2) delete-mid-flight must not resurrect a removed row ───────────────────


def test_delete_mid_flight_skips_persist_and_reraises_cancellederror(store, hermetic_execute):
    """delete_session marks the run `deleted` and cancels its task WITHOUT
    setting cancel_requested (that flag is reserved for the user-cancel path).
    execute()'s except CancelledError must therefore re-raise (this isn't a
    user stop) — and the finally must still skip persist() so the row
    delete_session just removed is never resurrected."""

    async def never_returns(*a, **k):
        await asyncio.sleep(60)

    import api.run_driver as rd
    rd_orig = rd.pipeline.run
    rd.pipeline.run = never_returns
    try:
        run = store.create("u1", "brief")

        async def go():
            run.task = asyncio.ensure_future(run_driver.execute(run, []))
            await asyncio.sleep(0)  # let execute() start and reach the await inside pipeline.run

            removed = store.delete_session("u1", run.session_id)
            assert removed == 1
            assert run.deleted is True
            assert run.cancel_requested is False, (
                "delete must not masquerade as a user cancel"
            )

            with pytest.raises(asyncio.CancelledError):
                await run.task
            assert run.task.cancelled()

        asyncio.run(asyncio.wait_for(go(), timeout=5))
    finally:
        rd.pipeline.run = rd_orig

    # the row delete_session removed must stay gone — no resurrection
    assert store.get("u1", run.id) is None


# ── (3) token accounting survives the cancel unwind ──────────────────────────


def test_tokens_used_readable_after_cancel_unwinds_usage_scope(store, hermetic_execute, monkeypatch):
    """A cancel mid-pipeline still charges whatever tokens were spent before
    the stop: run_usage.total_tokens is read in the except handler AFTER the
    `with usage_scope():` block has already unwound. Pin that usage_scope's
    __exit__ only resets its ContextVar and never invalidates the Usage object
    the caller is holding, so metering can't silently zero out on cancel."""
    from core.llm import usage as usage_mod

    async def slow_then_meter(*a, **k):
        acc = usage_mod._USAGE.get()
        acc.input_tokens += 123  # tokens spent before the stop lands
        await asyncio.sleep(60)

    monkeypatch.setattr(run_driver.pipeline, "run", slow_then_meter)

    run = store.create("u1", "brief")

    async def go():
        run.task = asyncio.ensure_future(run_driver.execute(run, []))
        await asyncio.sleep(0)
        run.cancel_requested = True
        run.task.cancel()
        # a user-requested cancel is swallowed inside execute() (cancel_requested
        # is True), so the task completes normally with status "cancelled" —
        # it does NOT propagate CancelledError to its awaiter.
        await run.task

    asyncio.run(asyncio.wait_for(go(), timeout=5))
    assert run.status == "cancelled"
    assert run.tokens_used == 123, (
        "tokens spent before the cancel must still be charged — got "
        f"{run.tokens_used}"
    )


def test_terminal_status_publishes_after_exactly_one_successful_persist(
    store, hermetic_execute, monkeypatch
):
    """Delivered becomes public only after one durable final write."""
    hermetic_execute(_fake_flow())
    run = store.create("u1", "brief")
    original_persist = store.persist
    calls = 0

    def counting_persist(candidate):
        nonlocal calls
        calls += 1
        assert not any(
            event.get("type") == "status" and event.get("status") in {"delivered", "failed"}
            for event in candidate.events
        ), "terminal status became public before persistence"
        original_persist(candidate)

    monkeypatch.setattr(store, "persist", counting_persist)
    asyncio.run(run_driver.execute(run, []))

    terminal = [
        event for event in run.events
        if event.get("type") == "status" and event.get("status") in {"delivered", "failed"}
    ]
    assert calls == 1
    assert terminal == [{"type": "status", "status": "delivered"}]
    assert store.get("u1", run.id).status == "delivered"


def test_final_persist_failure_reports_failed_once_and_retains_live_run(
    store, hermetic_execute, monkeypatch
):
    """A final-write fault cannot publish delivered or discard recoverable state."""
    hermetic_execute(_fake_flow())
    run = store.create("u1", "brief")
    calls = 0

    def fail_persist(candidate):
        nonlocal calls
        calls += 1
        raise RuntimeError("secret database detail")

    monkeypatch.setattr(store, "persist", fail_persist)

    async def go():
        frames: list[str] = []

        async def consume():
            async for frame in sse.sse_stream(run):
                frames.append(frame)

        consumer = asyncio.create_task(consume())
        await asyncio.sleep(0)
        await run_driver.execute(run, [])
        await consumer
        return frames

    frames = asyncio.run(asyncio.wait_for(go(), timeout=5))
    terminal_frames = [
        frame for frame in frames
        if '"type": "status"' in frame
        and ('"status": "delivered"' in frame or '"status": "failed"' in frame)
    ]

    assert calls == 1
    assert len(terminal_frames) == 1 and '"status": "failed"' in terminal_frames[0]
    assert run.status == "failed"
    assert store._runs[run.id] is run, "failed final write must retain live recovery state"
    assert "secret database detail" not in str(run.log)
    assert any("final persistence failed (RuntimeError)" in entry["title"] for entry in run.log)


# ── (4) subscriber queues never leak across connect/disconnect cycles ───────


def test_sse_subscriber_queue_removed_on_every_disconnect_cycle():
    """N connect/disconnect cycles against a still-live (non-terminal) run must
    each remove their queue — a leaked queue would pin memory per reconnect
    and eventually receive events for a client that's long gone."""

    async def consume_forever(run: RunState) -> None:
        # nothing ever emits into this run, so this blocks on queue.get() until
        # the client "disconnects" — simulated below via the task's own cancel,
        # exactly how a real dropped HTTP connection unwinds the generator.
        async for _ in sse.sse_stream(run):
            pass

    async def go():
        run = RunState(id="run_leak", user_id="u1", title="t", brief="b", session_id="run_leak")

        for _ in range(20):
            task = asyncio.ensure_future(consume_forever(run))
            await asyncio.sleep(0)  # let it register its queue and suspend on queue.get()
            assert len(run.subscribers) == 1, "subscriber queue was never registered"
            task.cancel()  # simulates a client disconnect mid-stream
            with pytest.raises(asyncio.CancelledError):
                await task
            assert run.subscribers == [], "subscriber queue leaked after disconnect"

    asyncio.run(asyncio.wait_for(go(), timeout=5))


def test_sse_replay_boundary_does_not_duplicate_event():
    """An event appearing while replay snapshot is built must not also arrive
    through live queue. Snapshot + subscriber registration are synchronous, so
    ordering them snapshot-first creates an atomic handoff without miss or dup."""
    run = RunState(id="run_boundary", user_id="u1", title="t", brief="b")
    first = {"type": "status", "status": "queued"}
    boundary = {"type": "status", "status": "working"}

    class _EmitDuringSnapshot(list):
        def __iter__(self):
            if boundary not in self:
                run.emit(boundary)
            return super().__iter__()

    run.events = _EmitDuringSnapshot([first])

    async def go():
        stream = sse.sse_stream(run)
        frames = [await anext(stream), await anext(stream)]
        run.finish()
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
        return frames

    frames = asyncio.run(asyncio.wait_for(go(), timeout=5))
    assert sum('"status": "working"' in frame for frame in frames) == 1


# ── (5) reconnect-after-persist replays nothing, closes cleanly ─────────────


def test_reconnect_after_persist_replays_nothing_and_closes(store):
    """Once a run has been persisted (evicted to SQLite — persist() pops it
    from the live cache), a reconnect rehydrates via _from_row(), which never
    repopulates `events` (runtime-only by contract, see
    run_state_roundtrip.py's RUNTIME_ONLY set). The stream must still close
    cleanly (not hang) — but it replays NOTHING, so a client that reconnects
    to a finished run needs GET /runs/:id for the actual content. Pins the
    api/README.md wording fixed alongside this test."""
    run = store.create("u1", "brief")
    run.status = "delivered"
    run.report = "final report text"
    run.emit({"type": "report_done"})
    store.persist(run)

    rehydrated = store.get("u1", run.id)
    assert rehydrated.events == []

    async def go():
        frames = []
        async for frame in sse.sse_stream(rehydrated):
            frames.append(frame)
        return frames

    frames = asyncio.run(asyncio.wait_for(go(), timeout=3))
    assert frames == []
