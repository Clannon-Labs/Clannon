"""
SSE failure terminal-event harness.

Pins the delivery contract that a run FAILING mid-stream still closes its SSE
stream cleanly and never hangs a connected client. Distinct from tests/run_cancel.py
(which covers cooperative CANCELLATION); this covers the EXCEPTION fault path.

Hermetic: no live server, no real pipeline, no paid keys. The REAL
api.run_driver.execute() is driven with the pipeline call replaced by a test-double
that raises RuntimeError, so execute()'s own try/except/finally guard is under
test. Only the I/O calls execute() makes before and after the pipeline call are
stubbed:
  - core.pipeline.run (== run_driver.pipeline.run)
                         -> raises RuntimeError("injected pipeline fault")
  - STORE.session_turns  -> returns []   (_gather_session_files; no prior turns)
  - STORE.persist        -> no-op        (finally; no SQLite in hermetic env)
  - auth.model_prefs_get -> returns {}   (build_model_overrides; no DB)

auth.fetch_wiki is NOT needed: the fake pipeline.run never invokes the _prepare
callback, so that branch is never reached.

Cases
-----
1. exception_subscriber_first    - subscriber already connected when the exception fires
2. late_subscriber_after_failure - subscriber connects AFTER the run has already failed

Standalone mode prints a per-case TERMINATED-CLEANLY / HUNG table. If any case hangs
or omits the terminal event a needs-reviewer note is written to /home/amrit/.clannon_proposal
and the process exits 1. The adapter is NOT modified; the gap is reported.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import pathlib
import sys
from collections.abc import Awaitable, Callable

# When invoked as a script (python tests/sse_failure_terminal.py from backend/),
# Python adds tests/ to sys.path, not backend/. Insert backend/ so the api/* and
# foundation/* packages are importable in both script and pytest modes.
if __name__ == "__main__":
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from api.run_state import RunState, TERMINAL_STATUSES  # noqa: F401 — imported for callers
from api import sse
import api.run_driver as run_driver
import core.pipeline as _pipeline_mod


# ---------------------------------------------------------------------------
# hermetic patch context
# ---------------------------------------------------------------------------


async def _injected_pipeline_fault(*args, **kwargs) -> None:
    raise RuntimeError("injected pipeline fault")


@contextlib.contextmanager
def _hermetic_patches():
    """
    Patch the I/O surfaces execute() touches so the test stays hermetic, and
    replace pipeline.run with a fault-injecting stub. The real execute() body
    (try/except/finally) is what's under test.
    """
    orig_pipeline_run = run_driver.pipeline.run
    orig_session_turns = run_driver.STORE.session_turns
    orig_persist = run_driver.STORE.persist
    orig_model_prefs_get = run_driver.auth.model_prefs_get
    try:
        run_driver.pipeline.run = _injected_pipeline_fault
        run_driver.STORE.session_turns = lambda *a, **kw: []
        run_driver.STORE.persist = lambda *a, **kw: None
        run_driver.auth.model_prefs_get = lambda *a, **kw: {}
        yield
    finally:
        run_driver.pipeline.run = orig_pipeline_run
        run_driver.STORE.session_turns = orig_session_turns
        run_driver.STORE.persist = orig_persist
        run_driver.auth.model_prefs_get = orig_model_prefs_get


def _fresh_run() -> RunState:
    return RunState(
        id="run_fail_t", user_id="u_test", title="t", brief="b", session_id="run_fail_t"
    )


# ---------------------------------------------------------------------------
# event checkers
# ---------------------------------------------------------------------------


def _parse_event(frame: str) -> dict:
    return json.loads(frame.split("data: ", 1)[1])


def _has_failed_status(frames: list[str]) -> bool:
    for frame in frames:
        ev = _parse_event(frame)
        if ev.get("type") == "status" and ev.get("status") == "failed":
            return True
    return False


def _has_message_done(frames: list[str]) -> bool:
    for frame in frames:
        if _parse_event(frame).get("type") == "message_done":
            return True
    return False


# ---------------------------------------------------------------------------
# case implementations
# ---------------------------------------------------------------------------


async def _case_subscriber_first() -> list[str]:
    """
    Client subscribes BEFORE the run starts. When execute()'s pipeline call raises,
    the real except/finally guard must deliver the terminal failed-status event and
    message_done, then close via the None sentinel from run.finish(). A regression
    where message_done moves out of finally or an early return skips run.finish()
    would make this case hang past the wait_for timeout.
    """
    run = _fresh_run()
    frames: list[str] = []

    async def consume() -> None:
        async for frame in sse.sse_stream(run):
            frames.append(frame)

    with _hermetic_patches():
        consumer = asyncio.create_task(consume())
        # yield so consume() runs to its first queue.get() suspension, registering
        # the subscriber queue before execute() emits any events
        await asyncio.sleep(0)
        await run_driver.execute(run)

    await consumer  # must complete, not hang; proves the None sentinel was sent
    return frames


async def _case_late_subscriber() -> list[str]:
    """
    Client connects AFTER the run has already failed. The SSE replay path must
    serve the buffered terminal events (written by the real execute() finally) then
    short-circuit on TERMINAL_STATUSES (sse.py:31) without hanging on queue.get().
    """
    run = _fresh_run()

    with _hermetic_patches():
        await run_driver.execute(run)  # all events buffered into run.events

    frames: list[str] = []
    async for frame in sse.sse_stream(run):
        frames.append(frame)
    return frames


# ---------------------------------------------------------------------------
# CASES registry used by both pytest and the standalone table runner
# ---------------------------------------------------------------------------

CASES: list[tuple[str, Callable[[], Awaitable[list[str]]]]] = [
    ("exception_subscriber_first", _case_subscriber_first),
    ("late_subscriber_after_failure", _case_late_subscriber),
]

_TIMEOUT = 5.0


# ---------------------------------------------------------------------------
# pytest tests (primary CI surface)
# ---------------------------------------------------------------------------


def test_exception_subscriber_first() -> None:
    """SSE stream closes with failed-status and message_done when subscriber is already connected."""

    async def go() -> None:
        frames = await _case_subscriber_first()
        assert _has_failed_status(frames), (
            "failed-status event missing — client left without a terminal event on pipeline exception"
        )
        assert _has_message_done(frames), (
            "message_done missing — conversational channel not closed on pipeline exception"
        )

    asyncio.run(asyncio.wait_for(go(), timeout=_TIMEOUT))


def test_late_subscriber_gets_buffered_terminal_and_closes() -> None:
    """Late subscriber replays buffered failure events and exits cleanly without hanging."""

    async def go() -> None:
        frames = await _case_late_subscriber()
        assert _has_failed_status(frames), (
            "failed-status event missing from buffered replay — late subscriber left uninformed of failure"
        )
        assert _has_message_done(frames), (
            "message_done missing from buffered replay — late subscriber sees incomplete event stream"
        )

    asyncio.run(asyncio.wait_for(go(), timeout=_TIMEOUT))


# ---------------------------------------------------------------------------
# standalone table runner
# ---------------------------------------------------------------------------


async def _run_case(
    name: str, fn: Callable[[], Awaitable[list[str]]]
) -> tuple[str, bool, list[str] | None]:
    try:
        frames = await asyncio.wait_for(fn(), timeout=_TIMEOUT)
        ok = _has_failed_status(frames) and _has_message_done(frames)
        return name, ok, frames
    except asyncio.TimeoutError:
        return name, False, None


async def _main() -> int:
    print("\nSSE failure terminal-event harness")
    print("=" * 60)

    results: list[tuple[str, bool, list[str] | None]] = []
    for name, fn in CASES:
        label, ok, frames = await _run_case(name, fn)
        if ok:
            verdict = "TERMINATED-CLEANLY"
        elif frames is None:
            verdict = "HUNG"
        else:
            verdict = "MISSING-TERMINAL"
        results.append((label, ok, frames))
        print(f"  {verdict:<22}  {label}")

    print()

    failures = [(n, f) for n, ok, f in results if not ok]
    if not failures:
        print("All cases TERMINATED-CLEANLY. SSE failure delivery contract pinned.")
        return 0

    note_path = "/home/amrit/.clannon_proposal"
    lines: list[str] = [
        "needs-reviewer: SSE failure terminal-event harness found real robustness gap(s)\n\n"
    ]
    for n, frames in failures:
        if frames is None:
            lines.append(
                f"HUNG: {n}\n"
                f"  Stream did not close within {_TIMEOUT}s after a pipeline exception.\n"
                "  A real client would be left hanging indefinitely.\n\n"
            )
        else:
            lines.append(
                f"MISSING-TERMINAL: {n}\n"
                "  Stream closed but lacked a failed-status event or message_done.\n"
                "  A real client would not know the run failed.\n\n"
            )
    lines.append(
        "Do NOT patch api/sse.py or api/run_driver.py to silence this.\n"
        "Investigate WHY the terminal event is absent or the stream is hanging\n"
        "and fix the root cause.\n"
    )
    with open(note_path, "w") as fh:
        fh.writelines(lines)

    print(f"REAL ROBUSTNESS GAP(S) detected. needs-reviewer note written to {note_path}")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
