"""Tests for the orchestrator Flow stage (entry point). The reasoning core
(run_loop) is faked here — the stage's job is Flow handling: response storage,
the timeout, and degrading gracefully (never a blank failure) when the loop times
out, hits a provider rate-limit storm, or faults. Memory writes are NO LONGER done
here — they are deferred to a post-filter site (see tests/memory_write_timing.py)."""

import asyncio

import settings
from foundation import Flow, NormalizedInput, Origin, OrchestratorResponse
from registry.capabilities import ExpertFindings
from core.orchestrator import orchestrator as stage


def _flow():
    return Flow.new(NormalizedInput(modality="text", content_type="text/plain", content="hi"), "s")


def test_stage_happy_path_sets_response_and_journal(monkeypatch):
    answer = "Here is a substantial, real answer to the user's question. " * 5  # >200 chars => substantive
    async def fake_loop(normalized, ports, ctx):
        return OrchestratorResponse(text=answer, confidence=0.8)
    monkeypatch.setattr(stage, "run_loop", fake_loop)

    out = asyncio.run(stage.run(_flow()))
    assert out.status.value == "ok"
    assert out.ctx.orchestrator_response.text == answer
    assert any(e.origin == Origin.ORCHESTRATOR for e in out.journal)
    # the stage NO LONGER writes memory — that is deferred to a post-filter site so a
    # draft the filter blocks never seeds memory (see tests/memory_write_timing.py).
    assert not hasattr(out.ctx, "memory_writes_requested")


def test_stage_degrades_gracefully_on_loop_error(monkeypatch):
    async def boom(normalized, ports, ctx):
        raise RuntimeError("loop broke")
    monkeypatch.setattr(stage, "run_loop", boom)

    out = asyncio.run(stage.run(_flow()))
    # never a blank failure: the run advances with an honest degraded answer
    assert out.status.value == "ok"
    resp = out.ctx.orchestrator_response
    assert resp.metadata["degraded"] is True and resp.metadata["cause"] == "error"
    assert resp.text                                              # a real, non-empty reason
    assert any(getattr(e, "kind", "") == "warning" for e in out.ctx.decision_log)


def test_stage_degrades_gracefully_on_timeout(monkeypatch):
    monkeypatch.setattr(settings, "ORCHESTRATOR", settings.ORCHESTRATOR.model_copy(update={"timeout_s": 0.01}))

    async def slow(normalized, ports, ctx):
        await asyncio.sleep(0.1)
        return OrchestratorResponse(text="late")
    monkeypatch.setattr(stage, "run_loop", slow)

    out = asyncio.run(stage.run(_flow()))
    assert out.status.value == "ok"
    resp = out.ctx.orchestrator_response
    assert resp.metadata["degraded"] is True and resp.metadata["cause"] == "timeout"
    assert "try again" in resp.text.lower()


def test_stage_salvages_partial_findings_on_rate_limit(monkeypatch):
    # the loop gathered one expert's findings, then every provider 429'd
    async def rate_limited(normalized, ports, ctx):
        ctx.expert_findings.append(
            ExpertFindings(expert="web.research", ref="abc123",
                           full_content="Cursor Pro is $20/month.", citations=[])
        )
        raise RuntimeError("All models failed: 429 RESOURCE_EXHAUSTED quota exceeded")
    monkeypatch.setattr(stage, "run_loop", rate_limited)

    out = asyncio.run(stage.run(_flow()))
    assert out.status.value == "ok"
    resp = out.ctx.orchestrator_response
    assert resp.metadata["cause"] == "rate_limit"
    # the gathered finding is salvaged into the degraded answer, attributed + referenced
    assert "Cursor Pro is $20/month." in resp.text
    assert "Web research" in resp.text
    assert resp.finding_refs == ["abc123"]

# NOTE: "a memory fault never fails a delivered turn" now lives in
# tests/memory_write_timing.py (test_memory_fault_never_fails_persist), because the
# memory write moved out of this stage to the post-filter persist site.
