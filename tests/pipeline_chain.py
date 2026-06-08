"""
Hermetic end-to-end check of the reasoning + output half of the pipeline:
normalizer -> verifier -> orchestrator -> output_filter -> delivery, with the LLM
calls mocked. Intake + sanitizer are skipped here because the sanitizer needs a
live ClamAV daemon; the full live run is the credits-gated e2e.
"""

import asyncio

from foundation import Flow
from core import normalizer, orchestrator, verifier
from core.verifier.utils import verification_result
from core.orchestrator.schemas import OrchestratorDecision
from security.filter import run as filter_run
from security.filter.schemas import FilterResult
from delivery import run as delivery_run

import core.verifier.verifier as verifier_mod
import core.orchestrator.loop as loop_mod
import security.filter.filter as filter_mod


def test_reasoning_and_output_chain(monkeypatch, capsys):
    async def fake_verify(normalized, deterministic):
        return verification_result(proceed=True, normalized=normalized)
    monkeypatch.setattr(verifier_mod, "verify_with_llm", fake_verify)

    async def fake_decide(normalized, hydration, obs, turn, *, force_answer=False):
        return OrchestratorDecision(kind="answer", answer_text="final answer", confidence=0.9)
    monkeypatch.setattr(loop_mod.advisor, "decide", fake_decide)

    async def fake_filter(response, findings):
        return FilterResult(proceed=True)
    monkeypatch.setattr(filter_mod, "_filter", fake_filter)

    flow = Flow.new("research vraksha", "s", user_id="u")
    out = asyncio.run(Flow.chain(
        flow, [normalizer.run, verifier.run, orchestrator.run, filter_run, delivery_run]
    ))

    assert out.status.value == "ok"
    assert out.ctx.final_response == "final answer"
    assert "final answer" in capsys.readouterr().out
