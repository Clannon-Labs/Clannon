"""Tests for the output filter stage (security/filter)."""

import asyncio

from foundation import Flow, NormalizedInput, OrchestratorResponse
import security.filter.filter as filter_stage
from security.filter.schemas import FilterResult


def _flow(text="hello"):
    flow = Flow.new(NormalizedInput(modality="text", content_type="text/plain", content="q"), "s")
    flow.ctx.orchestrator_response = OrchestratorResponse(text=text, confidence=0.9)
    return flow


def test_filter_proceeds(monkeypatch):
    async def fake(response, findings, memory, tool_calls):
        return FilterResult(proceed=True)
    monkeypatch.setattr(filter_stage, "_filter", fake)

    out = asyncio.run(filter_stage.run(_flow()))
    assert out.status.value == "ok"
    assert out.ctx.filter_result.proceed is True


def test_filter_blocks_unsafe(monkeypatch):
    async def fake(response, findings, memory, tool_calls):
        return FilterResult(proceed=False, blocked=True, reason="policy")
    monkeypatch.setattr(filter_stage, "_filter", fake)

    out = asyncio.run(filter_stage.run(_flow()))
    assert out.status.value == "blocked"
    assert out.ctx.filter_blocked is True


def test_groundedness_defaults_to_not_applicable():
    # CB5 earned-seal default — a FilterResult built without an explicit verdict
    # must never silently read as "checked and grounded".
    result = FilterResult(proceed=True)
    assert result.groundedness == "not_applicable"
    assert result.checks_performed == []


def test_earned_seal_survives_the_pass_path(monkeypatch):
    # The CB5 seal must reach ctx.filter_result on a PASS, not just on a block —
    # this is the exact gap ("set but never read") the CB5 proposal found.
    async def fake(response, findings, memory, tool_calls):
        return FilterResult(
            proceed=True,
            groundedness="grounded",
            checks_performed=["safety", "pii_or_secret", "ungrounded_claim", "prompt_injection"],
        )
    monkeypatch.setattr(filter_stage, "_filter", fake)

    out = asyncio.run(filter_stage.run(_flow()))
    assert out.ctx.filter_result.groundedness == "grounded"
    assert out.ctx.filter_result.checks_performed == [
        "safety", "pii_or_secret", "ungrounded_claim", "prompt_injection",
    ]


def test_proceed_true_does_not_require_grounded():
    # Anti-rubber-stamp: a safe-but-thinly-grounded draft is a valid, distinct
    # verdict — the schema must not force "grounded" just because proceed=true.
    result = FilterResult(proceed=True, groundedness="partial")
    assert result.proceed is True
    assert result.groundedness == "partial"
