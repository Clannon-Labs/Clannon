"""
Run-lifecycle concurrency invariants (API & Runtime specialist audit, 2026-07-26).

Targets the races the route layer's comments *claim* can't happen, and pins the
ones that are actually correct today so a future edit can't quietly break them.
Hermetic: no live server, no real pipeline, no paid keys — same fake-flow /
monkeypatch conventions as tests/sse_terminal_order.py and
tests/sse_failure_terminal.py.

Findings this file backs (see reports/api/ for the write-up):

1. "cancel can never race task registration" (app.py create_run/follow_up_run
   comment) is true TODAY only because `LocalArtifactStore.put` is a coroutine
   that never actually suspends (plain synchronous `write_bytes`, no real
   await). `test_cancel_can_race_task_registration_if_persist_inputs_suspends`
   proves the invariant is an accident of that implementation detail, not a
   structural guarantee: swap in any genuinely-async store (S3, aiofiles, a DB
   call) and a concurrent cancel can win the race, get told "cancelled", have
   it persisted — and then the orphaned task keeps running the real pipeline
   and silently overwrites that row with "delivered" moments later. That is a
   simultaneous violation of "exactly one terminal status + one final
   persistence action" and "degrade honestly" (a cancelled client is lied to).
   `test_no_cancel_race_today_with_the_real_artifact_store` pins that the
   accident holds for the actual `LocalArtifactStore` shipped today.
2. Delete-mid-flight (`RunStore.delete_session`) does NOT set `cancel_requested`
   — confirmed correct: `execute()`'s `except CancelledError` re-raises (a
   delete is not a user cancel), and the `finally` still skips `persist()`
   because `run.deleted` is set. Pinned so it stays this way.
3. `run_usage.total_tokens`, read in the `except` handlers after the `with
   usage_scope(): ...` block has unwound, stays valid — `usage_scope`'s
   context manager only resets a ContextVar; it never mutates the `Usage`
   object callers hold a reference to. Pinned.
4. SSE subscriber queues are removed from `run.subscribers` on every
   disconnect, live or not — no leak across repeated connect/cancel cycles.
5. A reconnect to a run that has ALREADY been persisted (evicted from the
   in-memory store) replays zero buffered frames and closes immediately —
   `events` is deliberately runtime-only (tests/run_state_roundtrip.py), so
   `_from_row` never repopulates it. `api/README.md` previously read as if
   every reconnect replays the buffered sequence regardless; corrected there
   to say this only holds for a still-live run, and a client revisiting a
   finished run must fetch `GET /runs/:id` for content instead.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from api.run_state import RunState
from api.run_store import RunStore
from api import sse
import api.run_driver as run_driver


# ── shared fixtures ───────────────────────────────────────────────────────────


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """A RunStore backed by a throwaway SQLite file, wired into run_driver's own
    module-level reference (run_driver imported STORE by name, so patching
    api.run_store.STORE alone would miss it)."""
    from api import config

    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "lifecycle.db"))
    fresh = RunStore()
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


async def _simulate_create_run(store: RunStore, input_files: list) -> RunState:
    """Mirrors app.py's create_run ordering exactly: create the run (visible to
    request_cancel from this point on), await persist_inputs, THEN assign
    run.task. If persist_inputs ever actually suspends, a cancel can land in
    the gap between the first two steps and the third."""
    run = store.create("u1", "test brief")
    await run_driver.persist_inputs(run, input_files)
    run.task = asyncio.ensure_future(run_driver.execute(run, input_files))
    return run


def test_cancel_can_race_task_registration_if_persist_inputs_suspends(
    store, hermetic_execute, monkeypatch
):
    """With a realistically-async artifact store, a cancel arriving while
    persist_inputs is in flight wins the "no live task" branch, reports
    "cancelled", and persists it — then the still-running create path assigns
    the orphaned task anyway, which delivers and OVERWRITES the persisted
    "cancelled" row with "delivered". Proves app.py:365-368's "same tick, a
    cancel can never race a not-yet-tracked task" comment is an accident of
    LocalArtifactStore.put's implementation, not a structural guarantee."""
    hermetic_execute(_fake_flow())
    reached = asyncio.Event()
    release = asyncio.Event()
    monkeypatch.setattr(
        run_driver, "LocalArtifactStore", lambda: _SuspendingArtifactStore(reached, release)
    )
    input_file = SimpleNamespace(name="f.txt", data=b"hi", as_dict=lambda: {"name": "f.txt"})

    async def go():
        create_fut = asyncio.ensure_future(_simulate_create_run(store, [input_file]))
        await asyncio.wait_for(reached.wait(), timeout=2)

        # the run is registered and visible to request_cancel, but its task
        # handle is still None — exactly the window under test
        rid = next(iter(store._runs))
        assert store._runs[rid].task is None, (
            "run.task already assigned — the race window this test targets isn't open; "
            "the fixture no longer matches app.py's ordering"
        )

        outcome = store.request_cancel("u1", rid)
        assert outcome == "cancelled", "expected the no-live-task direct-finalize path"
        assert rid not in store._runs, "request_cancel's persist() should have evicted the run"

        persisted_after_cancel = store.get("u1", rid)
        assert persisted_after_cancel.status == "cancelled"

        # release persist_inputs; create_run finishes registering the (now
        # orphaned) task, whose pipeline still "delivers"
        release.set()
        run = await create_fut
        await run.task

        return rid

    rid = asyncio.run(asyncio.wait_for(go(), timeout=5))

    # the SAME run id now silently reads back as delivered — the cancel the
    # caller was told succeeded was overwritten without any signal
    resurrected = store.get("u1", rid)
    assert resurrected.status == "delivered", (
        "expected the orphaned task's delivery to have overwritten the cancelled row — "
        "if this now reads 'cancelled', the race no longer reproduces and this test "
        "should be re-examined, not loosened"
    )


def test_no_cancel_race_today_with_the_real_artifact_store(store, hermetic_execute):
    """Companion to the test above: pins that TODAY's actual LocalArtifactStore
    (synchronous write_bytes under an async def) never suspends, so
    persist_inputs never yields, so run.task really is assigned in the same
    scheduler tick as run creation — the safety net app.py relies on, made
    explicit so a future change to LocalArtifactStore is the trigger to
    revisit this, not a silent regression."""
    hermetic_execute(_fake_flow())
    input_file = SimpleNamespace(name="f.txt", data=b"hi", as_dict=lambda: {"name": "f.txt"})

    async def go():
        run = await _simulate_create_run(store, [input_file])
        # by the time _simulate_create_run returns, task assignment already
        # happened — no concurrent coroutine ever got a chance to run in between
        assert run.task is not None
        await run.task
        return run.id

    rid = asyncio.run(asyncio.wait_for(go(), timeout=5))
    assert store.get("u1", rid).status == "delivered"


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
