"""Bounded output-filter recovery: the orchestrator gets one or more chances to
revise a rejected draft, but the filter is always the final authority and the
loop fails closed after MAX_OUTPUT_RETRIES."""

import asyncio
from types import SimpleNamespace

from foundation import VrakshaContext, constants
import server.runs as runs_mod
from server.runs import RunState, _recover_from_filter_block


def _blocked_ctx() -> VrakshaContext:
    ctx = VrakshaContext.new(session_id="s", user_id="u", trace_id="t")
    ctx.filter_blocked = True
    ctx.filter_block_reason = "claim unsupported by findings"
    ctx.normalized_input = SimpleNamespace(modality="text", content="q")
    return ctx


class _FakeFlow:
    def __init__(self, ctx):
        self.ctx = ctx


def _patch_orchestration(monkeypatch):
    async def fake_run_loop(normalized, ports, ctx):
        return SimpleNamespace(text="revised draft", confidence=0.9)
    monkeypatch.setattr("core.orchestrator.loop.run_loop", fake_run_loop)
    monkeypatch.setattr("core.orchestrator.utils.wiring.build_default_ports", lambda ctx: object())


def test_retry_recovers_when_filter_passes(monkeypatch):
    _patch_orchestration(monkeypatch)

    # filter passes on the first revision
    async def fake_filter(flow):
        flow.ctx.filter_blocked = False
        return flow
    monkeypatch.setattr(runs_mod, "_OUTPUT_FILTER", fake_filter)

    flow = _FakeFlow(_blocked_ctx())
    run = RunState(id="r", user_id="u", title="t", brief="b")
    out = asyncio.run(_recover_from_filter_block(flow, run))

    assert out.ctx.filter_blocked is False          # recovered
    assert out.ctx.filter_retry_count == 1          # one revision was enough
    assert out.ctx.filter_feedback is None          # not left lingering


def test_retry_is_bounded_and_fails_closed(monkeypatch):
    _patch_orchestration(monkeypatch)

    # filter NEVER accepts — the loop must stop and stay blocked
    async def always_block(flow):
        flow.ctx.filter_blocked = True
        return flow
    monkeypatch.setattr(runs_mod, "_OUTPUT_FILTER", always_block)

    flow = _FakeFlow(_blocked_ctx())
    run = RunState(id="r", user_id="u", title="t", brief="b")
    out = asyncio.run(_recover_from_filter_block(flow, run))

    assert out.ctx.filter_retry_count == constants.MAX_OUTPUT_RETRIES  # bounded
    assert out.ctx.filter_blocked is True                             # fail closed
