"""
Hermetic resilience harness for core/warmup.py.

Pins the best-effort / non-blocking boot contract declared at warmup.py:10-13:

    "a warmup failure is logged and ignored — the lazy paths still load (and
    degrade) on demand, so warmup can never fail or slow a run."

Three warm targets are monkeypatched at their module-attribute seams:

    core.memory.embeddings.warm           async — awaited directly in _warm_embeddings
    core.memory.store.healthcheck         sync  — run via asyncio.to_thread in _warm_qdrant
    security.sanitizers.workers.text.warm sync  — run via asyncio.to_thread in _warm_sanitizer

No model download, no Qdrant connection, no spaCy/Presidio load, no network.

Fault classes tested (warmup.py:54 — the asyncio.gather of all three):

    (a) ALL-SUCCEED    all three targets invoked; warmup() returns None
    (b) EACH-RAISES    one target raises (transient error); warmup() still None; others still run
    (c) EACH-FALSE     one target returns False (resource unavailable); warmup() still None
    (d) CONCURRENT     all three start before the slow async target completes (gather, not sequential)

On any detected gap (warmup() raises or skips a remaining task), the harness
records a needs-reviewer note rather than patching warmup.py to force a green.
This mirrors the PR #51 store-fault pattern at the BOOT layer.

Distinct from tests/health_lifecycle.py (PR #72 api lifespan / health-endpoint
wiring test); this file pins the SOURCE-LEVEL warmup contract, not the API wiring.
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

# Safe pre-imports — heavy init (model download, Qdrant connect, spaCy load) is
# inside warm()/healthcheck() bodies, not at module level, so importing these is cheap.
import core.memory.embeddings as _emb_mod          # async warm() -> bool
import core.memory.store as _store_mod              # sync  healthcheck() -> bool
import security.sanitizers.workers.text as _text_mod  # sync  warm() -> bool

from core.warmup import warmup


# ── Verdict collector ──────────────────────────────────────────────────────

_RESULTS: list[tuple[str, str, str]] = []   # (fault_class, SWALLOWED/RAISED, YES/NO)
_GAPS: list[str] = []


def _record(fault_class: str, raised: bool, all_called: bool) -> None:
    verdict = "RAISED" if raised else "SWALLOWED"
    all_str = "YES" if all_called else "NO"
    _RESULTS.append((fault_class, verdict, all_str))
    if raised or not all_called:
        _GAPS.append(fault_class)


@pytest.fixture(scope="module", autouse=True)
def _print_summary():
    yield
    if not _RESULTS:
        return
    col = max(len(r[0]) for r in _RESULTS) + 2
    header = f"  {'Fault class':<{col}} {'Verdict':<12} All-3-attempted"
    sep = "=" * (len(header) + 2)
    print()
    print(sep)
    print("  warmup.py boot-path degrade-never-block contract harness")
    print(sep)
    print(header)
    print("  " + "-" * (len(header) - 2))
    for fault_class, verdict, all_three in _RESULTS:
        print(f"  {fault_class:<{col}} {verdict:<12} {all_three}")
    print(sep)
    all_swallowed = all(v == "SWALLOWED" for _, v, _ in _RESULTS)
    all_three_ok  = all(a == "YES"       for _, _, a in _RESULTS)
    overall = (
        "DEGRADES (contract holds)"
        if all_swallowed and all_three_ok
        else "RAISES or SKIPS (contract VIOLATED)"
    )
    print(f"  Boot posture: {overall}")
    print(sep)
    print()
    if _GAPS:
        print(f"  GAP(s): {', '.join(_GAPS)}")
        _write_needs_reviewer_note(_GAPS)
        print("  Wrote needs-reviewer note to ~/.clannon_proposal")
        print()


def _write_needs_reviewer_note(gaps: list[str]) -> None:
    path = os.path.expanduser("~/.clannon_proposal")
    note = (
        "\n# needs-reviewer: warmup.py degrade-never-block gap (boot layer)\n\n"
        "The warmup harness (backend/tests/warmup.py) detected that warmup() "
        "RAISED or skipped a remaining task in:\n\n"
        + "".join(f"  - {g}\n" for g in gaps)
        + "\n"
        "Expected contract (warmup.py:10-13): warmup() returns None and all three\n"
        "targets are invoked regardless of individual target failures.\n\n"
        "This is the BOOT-PATH twin of needs-reviewer #52 (store-fault gather gap).\n\n"
        "Options:\n"
        "  A. Add try/except around each _warm_* invocation inside asyncio.gather\n"
        "  B. Use asyncio.gather(..., return_exceptions=True) in warmup()\n"
        "  C. Wrap the whole gather in a try/except at the warmup() level\n\n"
        "Recommendation: B — return_exceptions=True is the most direct fix and\n"
        "preserves per-task isolation that the existing structure implies.\n"
    )
    with open(path, "a") as fh:
        fh.write(note)


# ── Spy helpers ────────────────────────────────────────────────────────────

class _CallLog:
    """Records which of the three warm targets were called during a run."""

    def __init__(self):
        self.tags: list[str] = []

    # async targets (embeddings.warm is a coroutine function)
    def async_returns(self, tag: str, value: bool):
        async def _f():
            self.tags.append(tag)
            return value
        return _f

    def async_raises(self, tag: str, exc: Exception):
        async def _f():
            self.tags.append(tag)
            raise exc
        return _f

    # sync targets (store.healthcheck + text.warm are called via asyncio.to_thread)
    def sync_returns(self, tag: str, value: bool):
        def _f():
            self.tags.append(tag)
            return value
        return _f

    def sync_raises(self, tag: str, exc: Exception):
        def _f():
            self.tags.append(tag)
            raise exc
        return _f

    @property
    def all_three(self) -> bool:
        return set(self.tags) >= {"emb", "store", "text"}


def _apply(monkeypatch, *, emb, store, text) -> None:
    monkeypatch.setattr(_emb_mod,   "warm",        emb)
    monkeypatch.setattr(_store_mod, "healthcheck", store)
    monkeypatch.setattr(_text_mod,  "warm",        text)


def _run_warmup() -> bool:
    """Run warmup(). Returns True if warmup() RAISED, False if it returned normally."""
    try:
        asyncio.run(warmup())
        return False
    except Exception:
        return True


# ── (a) ALL-SUCCEED ────────────────────────────────────────────────────────

def test_all_succeed_warmup_returns_none(monkeypatch):
    """All three targets succeed; warmup() returns None and all three are invoked."""
    calls = _CallLog()
    _apply(monkeypatch,
           emb=calls.async_returns("emb", True),
           store=calls.sync_returns("store", True),
           text=calls.sync_returns("text", True))

    raised = _run_warmup()

    _record("ALL-SUCCEED", raised, calls.all_three)
    assert not raised, "warmup() RAISED on all-succeed path — contract broken"
    assert calls.all_three, f"not all three targets were invoked; got {calls.tags}"


# ── (b) EACH-RAISES ────────────────────────────────────────────────────────

@pytest.mark.parametrize("who,exc,label", [
    (
        "emb",
        RuntimeError("embeddings download failed"),
        "RAISES: embeddings-download error",
    ),
    (
        "store",
        ConnectionRefusedError("Qdrant connection refused"),
        "RAISES: Qdrant connection error",
    ),
    (
        "text",
        ImportError("spaCy/Presidio init failed"),
        "RAISES: spaCy-Presidio init error",
    ),
])
def test_one_raises_warmup_still_completes_and_others_run(who, exc, label, monkeypatch):
    """One target raises; warmup() still returns None and the other two still run.

    This pins the asyncio.gather contract: because each _warm_* coroutine
    catches its own exception, gather never sees a raise and never cancels
    the remaining coroutines.
    """
    calls = _CallLog()
    _apply(monkeypatch,
           emb=(calls.async_raises("emb", exc)
                if who == "emb" else calls.async_returns("emb", True)),
           store=(calls.sync_raises("store", exc)
                  if who == "store" else calls.sync_returns("store", True)),
           text=(calls.sync_raises("text", exc)
                 if who == "text" else calls.sync_returns("text", True)))

    raised = _run_warmup()

    _record(label, raised, calls.all_three)

    if raised:
        pytest.fail(
            f"{label}: warmup() RAISED — expected the exception to be swallowed. "
            "This is a degrade-never-block contract violation."
        )
    if not calls.all_three:
        pytest.fail(
            f"{label}: not all three targets were invoked (got {calls.tags}). "
            "One task raising appears to have prevented the remaining tasks from "
            "running — asyncio.gather may need return_exceptions=True."
        )


# ── (c) EACH-RETURNS-FALSE ─────────────────────────────────────────────────

@pytest.mark.parametrize("who,label", [
    ("emb",   "FALSE: embeddings unavailable"),
    ("store", "FALSE: Qdrant down/disabled"),
    ("text",  "FALSE: sanitizer build-deferred"),
])
def test_one_false_warmup_still_completes(who, label, monkeypatch):
    """A False return (resource unavailable/deferred) is swallowed; warmup() returns None."""
    calls = _CallLog()
    _apply(monkeypatch,
           emb=(calls.async_returns("emb", False)
                if who == "emb" else calls.async_returns("emb", True)),
           store=(calls.sync_returns("store", False)
                  if who == "store" else calls.sync_returns("store", True)),
           text=(calls.sync_returns("text", False)
                 if who == "text" else calls.sync_returns("text", True)))

    raised = _run_warmup()

    _record(label, raised, calls.all_three)
    assert not raised, f"{label}: warmup() RAISED on False return — contract broken"
    assert calls.all_three, f"{label}: not all three targets called; got {calls.tags}"


# ── (d) CONCURRENT gather probe ────────────────────────────────────────────

def test_warmup_gathers_concurrently_not_sequentially(monkeypatch):
    """All three targets start before the slow async target completes.

    Proof: the async emb target blocks on a barrier. The sync store and text
    targets run in asyncio.to_thread while emb is blocked. The releaser polls
    until both have logged, then unblocks emb.  If tasks ran sequentially
    (await _warm_emb(); await _warm_qdrant(); ...) the store/text entries
    would appear AFTER emb_done, not before.
    """
    calls: list[str] = []

    async def _probe():
        barrier = asyncio.Event()

        async def slow_emb():
            calls.append("emb_start")
            await barrier.wait()
            calls.append("emb_done")
            return True

        def fast_store():
            calls.append("store")
            return True

        def fast_text():
            calls.append("text")
            return True

        monkeypatch.setattr(_emb_mod,   "warm",        slow_emb)
        monkeypatch.setattr(_store_mod, "healthcheck", fast_store)
        monkeypatch.setattr(_text_mod,  "warm",        fast_text)

        async def _releaser():
            for _ in range(100):
                await asyncio.sleep(0.01)
                if "store" in calls and "text" in calls:
                    barrier.set()
                    return
            barrier.set()  # safety: never leave emb blocked

        await asyncio.gather(warmup(), _releaser())

    asyncio.run(_probe())

    assert "emb_start" in calls, "embeddings target was never called"
    assert "store"     in calls, "store target was never called"
    assert "text"      in calls, "text target was never called"
    assert calls.index("store") < calls.index("emb_done"), (
        "store ran AFTER emb_done — tasks appear to be sequential, not concurrent"
    )
    assert calls.index("text") < calls.index("emb_done"), (
        "text ran AFTER emb_done — tasks appear to be sequential, not concurrent"
    )

    _record("CONCURRENT gather probe", False, True)
