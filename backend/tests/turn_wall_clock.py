"""The whole-turn wall clock (audit finding #2).

One deadline (`ctx.turn_deadline`) is set at turn start and bounds BOTH the initial
orchestrator pass and every filter-revision. Previously each of ≤FILTER_MAX_REVISIONS
revisions got a FRESH copy of the orchestrator's own timeout, compounding to ~1440s/24min
with no outer kill. Now a revision budgets against the time REMAINING; budget exhausted ⇒
`wait_for` times out ⇒ fail closed. These prove the bound holds AND that a healthy
budget doesn't break legitimate recovery.
"""

import asyncio
import time
from types import SimpleNamespace

import settings
from foundation import VrakshaContext, constants
import core.pipeline as pipeline


def _blocked_ctx() -> VrakshaContext:
    ctx = VrakshaContext.new(session_id="s", user_id="u", trace_id="t")
    ctx.filter_blocked = True
    ctx.filter_block_reason = "claim unsupported by findings"
    ctx.normalized_input = SimpleNamespace(modality="text", content="q")
    return ctx


class _FakeFlow:
    def __init__(self, ctx):
        self.ctx = ctx


def _patch(monkeypatch, run_loop):
    # the recovery imports these lazily from their modules, so patch them there
    monkeypatch.setattr("core.orchestrator.loop.run_loop", run_loop)
    monkeypatch.setattr("core.orchestrator.utils.wiring.build_default_ports", lambda ctx: object())

    async def always_block(flow):
        flow.ctx.filter_blocked = True   # filter never accepts — exercise the full loop
        return flow
    monkeypatch.setattr(pipeline, "output_filter_run", always_block)


def test_revision_fails_closed_when_turn_budget_exhausted(monkeypatch):
    """An exhausted whole-turn deadline gives the revision ~0 budget, so a revision
    that would take real time times out and fails closed — it does NOT get a fresh
    full orchestrator timeout (the compounding bug that allowed a ~24min runaway)."""
    async def slow_run_loop(normalized, ports, ctx):
        await asyncio.sleep(0.10)  # completes on a fresh full budget; must NOT here
        return SimpleNamespace(text="revised", confidence=0.9)
    _patch(monkeypatch, slow_run_loop)

    ctx = _blocked_ctx()
    ctx.turn_deadline = time.monotonic() - 1.0   # whole-turn budget already spent
    out = asyncio.run(pipeline.recover_from_filter_block(_FakeFlow(ctx)))

    assert out.ctx.failed is True             # timed out on the whole-turn deadline → fail closed
    assert out.ctx.filter_retry_count == 1    # one attempt, then the shared budget cut it off


def test_revision_proceeds_with_healthy_turn_budget(monkeypatch):
    """A healthy whole-turn deadline leaves ample budget, so revisions run normally —
    the fix bounds runaway WITHOUT breaking legitimate recovery."""
    async def fast_run_loop(normalized, ports, ctx):
        return SimpleNamespace(text="revised", confidence=0.9)
    _patch(monkeypatch, fast_run_loop)

    ctx = _blocked_ctx()
    ctx.turn_deadline = time.monotonic() + 100.0   # plenty of budget remaining
    out = asyncio.run(pipeline.recover_from_filter_block(_FakeFlow(ctx)))

    assert out.ctx.failed is False                                       # no spurious timeout
    assert out.ctx.filter_retry_count == constants.FILTER_MAX_REVISIONS  # ran the full loop
    assert out.ctx.orchestrator_response.text == "revised"              # revisions actually happened


def test_turn_wall_clock_is_above_one_pass():
    """The ceiling must exceed a single legitimate pass, so a normal turn is never cut
    short and the bound only ever catches compounding/runaway."""
    assert settings.ORCHESTRATOR.turn_wall_clock_s > settings.ORCHESTRATOR.timeout_s
