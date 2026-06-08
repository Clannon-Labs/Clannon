"""Tests for the delivery stage (CLI adapter)."""

import asyncio

from foundation import Flow, NormalizedInput, OrchestratorResponse
import delivery.delivery as delivery_stage


def test_delivery_sets_final_response_and_prints(capsys):
    flow = Flow.new(NormalizedInput(modality="text", content_type="text/plain", content="q"), "s")
    flow.ctx.orchestrator_response = OrchestratorResponse(text="the answer", confidence=0.9)

    out = asyncio.run(delivery_stage.run(flow))
    assert out.status.value == "ok"
    assert out.ctx.final_response == "the answer"
    assert "the answer" in capsys.readouterr().out
