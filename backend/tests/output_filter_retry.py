"""The single, shared, fail-closed output-filter recovery
(`core.pipeline.recover_from_filter_block`): the orchestrator gets bounded chances
to revise a rejected draft, but the filter is always the final authority and the
loop fails closed after FILTER_MAX_REVISIONS. ONE loop — used by both the CLI
pipeline and the web run driver — narrated on the shared decision log."""

import asyncio
from types import SimpleNamespace

from foundation import VrakshaContext
import settings
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


def _patch_orchestration(monkeypatch):
    async def fake_run_loop(normalized, ports, ctx):
        return SimpleNamespace(text="revised draft", confidence=0.9)
    # the recovery imports these lazily from their modules, so patch them there
    monkeypatch.setattr("core.orchestrator.loop.run_loop", fake_run_loop)
    monkeypatch.setattr("core.orchestrator.utils.wiring.build_default_ports", lambda ctx: object())


def test_recovery_succeeds_when_filter_passes(monkeypatch):
    _patch_orchestration(monkeypatch)

    async def fake_filter(flow):
        flow.ctx.filter_blocked = False     # filter accepts the revised draft
        return flow
    monkeypatch.setattr(pipeline, "output_filter_run", fake_filter)

    flow = _FakeFlow(_blocked_ctx())
    out = asyncio.run(pipeline.recover_from_filter_block(flow))

    assert out.ctx.filter_blocked is False                # recovered
    assert out.ctx.filter_retry_count == 1                # one revision was enough
    assert out.ctx.filter_feedback is None                # not left lingering
    assert out.ctx.orchestrator_response.text == "revised draft"


def test_recovery_is_bounded_and_fails_closed(monkeypatch):
    _patch_orchestration(monkeypatch)

    async def always_block(flow):
        flow.ctx.filter_blocked = True      # filter NEVER accepts
        return flow
    monkeypatch.setattr(pipeline, "output_filter_run", always_block)

    flow = _FakeFlow(_blocked_ctx())
    out = asyncio.run(pipeline.recover_from_filter_block(flow))

    assert out.ctx.filter_retry_count == settings.SECURITY.filter_max_revisions  # bounded
    assert out.ctx.filter_blocked is True                               # fail closed


def test_recovery_narrates_each_attempt_on_the_decision_log(monkeypatch):
    _patch_orchestration(monkeypatch)

    async def always_block(flow):
        flow.ctx.filter_blocked = True
        return flow
    monkeypatch.setattr(pipeline, "output_filter_run", always_block)

    flow = _FakeFlow(_blocked_ctx())
    asyncio.run(pipeline.recover_from_filter_block(flow))

    notices = [
        e for e in flow.ctx.decision_log
        if getattr(e, "kind", "") == "warning" and "revising" in getattr(e, "message", "")
    ]
    assert len(notices) == settings.SECURITY.filter_max_revisions  # one per attempt, on the shared log
