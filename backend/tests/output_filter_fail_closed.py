"""The output filter fails CLOSED on infra/LLM faults (security/filter).

The filter is the sole output gate. If adjudication itself breaks (the model is
unreachable, the structured-output call throws, an unexpected exception escapes),
the stage must NOT fall through to delivery: it converts the fault into a
`flow.fail`, so `should_stop` is True and the unfiltered draft is never delivered.
A fault is a fault, not a block (`filter_blocked` stays False) and not a pass
(`filter_result` is never set). These characterize current behavior; they do not
change the filter.
"""

import asyncio

from foundation import (
    Flow,
    FilterError,
    ModelUnavailableError,
    NormalizedInput,
    OrchestratorResponse,
    Status,
)
import security.filter.filter as filter_stage


def _flow(text="draft response"):
    flow = Flow.new(NormalizedInput(modality="text", content_type="text/plain", content="q"), "s")
    flow.ctx.orchestrator_response = OrchestratorResponse(text=text, confidence=0.9)
    return flow


def _spy_fail(monkeypatch):
    """Capture the exception object actually handed to flow.fail, then run the real fail()."""
    captured = {}
    original = Flow.fail

    def spy(self, error, origin, started_at=None):
        captured["error"] = error
        captured["origin"] = origin
        return original(self, error, origin, started_at)

    monkeypatch.setattr(Flow, "fail", spy)
    return captured


def _assert_fails_closed(out):
    """Every fault path lands here: stopped, errored, draft not delivered, not blocked."""
    assert out.status is Status.ERROR        # not OK -> the chain never reached flow.next
    assert out.ok is False
    assert out.should_stop is True           # delivery (the next stage) is skipped
    assert out.errored is True
    assert out.ctx.failed is True
    # a fault is distinct from a content block, and no draft was adjudicated through
    assert out.ctx.filter_blocked is False
    assert out.ctx.filter_result is None


def test_generic_infra_fault_is_wrapped_in_filtererror_and_fails(monkeypatch):
    # adjudication blows up with a non-Vraksha exception (e.g. a socket reset)
    boom = RuntimeError("qdrant socket reset")

    async def fake(response, findings, memory, tool_calls):
        raise boom
    monkeypatch.setattr(filter_stage, "_filter", fake)
    captured = _spy_fail(monkeypatch)

    out = asyncio.run(filter_stage.run(_flow()))

    _assert_fails_closed(out)
    # the bare exception is wrapped into a FilterError that preserves the cause
    assert isinstance(captured["error"], FilterError)
    assert captured["error"].cause is boom
    assert out.error.startswith("output filter failed:")


def test_model_unavailable_fault_fails_closed(monkeypatch):
    # the filter LLM is unreachable: an InfrastructureError, passed through as-is
    fault = ModelUnavailableError("timeout after 5s", model="filter")

    async def fake(response, findings, memory, tool_calls):
        raise fault
    monkeypatch.setattr(filter_stage, "_filter", fake)
    captured = _spy_fail(monkeypatch)

    out = asyncio.run(filter_stage.run(_flow()))

    _assert_fails_closed(out)
    # ModelUnavailableError is handled by the first except arm and NOT re-wrapped
    assert captured["error"] is fault


def test_filter_error_from_adjudication_fails_closed(monkeypatch):
    # malformed structured output surfaces as FilterError; it must fail closed too
    fault = FilterError("filter LLM produced malformed output")

    async def fake(response, findings, memory, tool_calls):
        raise fault
    monkeypatch.setattr(filter_stage, "_filter", fake)
    captured = _spy_fail(monkeypatch)

    out = asyncio.run(filter_stage.run(_flow()))

    _assert_fails_closed(out)
    assert captured["error"] is fault        # passed through, not double-wrapped
