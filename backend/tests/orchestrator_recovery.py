"""Unit tests for orchestrator graceful-degradation helpers (utils/recovery):
classifying a loop failure and building an honest, LLM-free degraded answer from
whatever partial state the run gathered."""

from foundation import Flow, NormalizedInput
from registry.capabilities import ExpertFindings
from core.orchestrator.utils.recovery import (
    build_degraded_response,
    classify_failure,
    degraded_reason,
)


class _Boom(Exception):
    """An exception carrying an HTTP-style status_code, like the SDK's ModelHTTPError."""
    def __init__(self, msg, status_code=None):
        super().__init__(msg)
        self.status_code = status_code


def test_classify_plain_timeout():
    assert classify_failure(TimeoutError()) == "timeout"


def test_classify_unexpected_error():
    assert classify_failure(RuntimeError("null pointer somewhere")) == "error"


def test_classify_rate_limit_from_message():
    assert classify_failure(RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded")) == "rate_limit"
    assert classify_failure(RuntimeError("anthropic: usage limits reached")) == "rate_limit"


def test_classify_rate_limit_from_status_code():
    assert classify_failure(_Boom("model http error", status_code=429)) == "rate_limit"


def test_classify_rate_limit_inside_exception_group():
    # mirrors pydantic-ai's FallbackExceptionGroup: a wall of per-model 429s
    group = ExceptionGroup("All models from FallbackModel failed",
                           [_Boom("503 overloaded"), _Boom("429 quota", status_code=429)])
    assert classify_failure(group) == "rate_limit"


def test_classify_rate_limit_wins_over_timeout_in_chain():
    try:
        try:
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        except RuntimeError as inner:
            raise TimeoutError("loop wall clock") from inner
    except TimeoutError as exc:
        assert classify_failure(exc) == "rate_limit"


def test_classify_handles_cyclic_cause_without_hanging():
    a = RuntimeError("a"); b = RuntimeError("b")
    a.__cause__ = b; b.__cause__ = a            # pathological cycle
    assert classify_failure(a) == "error"       # terminates, no infinite recursion


def _ctx():
    # a fully-built context, exactly as the pipeline constructs it
    return Flow.new(NormalizedInput(modality="text", content_type="text/plain", content="hi"), "s").ctx


def test_degraded_reason_is_honest_and_actionable():
    for kind in ("rate_limit", "timeout", "error"):
        reason = degraded_reason(kind)
        assert reason and "try again" in reason.lower()


def test_degraded_response_with_no_findings_is_just_the_reason():
    resp = build_degraded_response(_ctx(), "timeout")
    assert resp.text == degraded_reason("timeout")
    assert resp.metadata == {"degraded": True, "cause": "timeout"}
    assert resp.finding_refs == []
    assert resp.confidence < 0.5


def test_degraded_response_salvages_and_attributes_partial_findings():
    ctx = _ctx()
    ctx.expert_findings.append(
        ExpertFindings(expert="web.research", ref="r1", full_content="Finding ONE body.")
    )
    ctx.expert_findings.append(
        ExpertFindings(expert="synthesis.writer", ref="r2", full_content="Finding TWO body.")
    )
    resp = build_degraded_response(ctx, "rate_limit")
    assert degraded_reason("rate_limit") in resp.text
    assert "Finding ONE body." in resp.text and "Finding TWO body." in resp.text
    assert "Web research" in resp.text and "Synthesis writer" in resp.text
    assert resp.finding_refs == ["r1", "r2"]


def test_degraded_response_skips_empty_findings_and_caps_size():
    ctx = _ctx()
    ctx.expert_findings.append(ExpertFindings(expert="x.y", ref="empty", full_content=""))
    ctx.expert_findings.append(
        ExpertFindings(expert="x.y", ref="big", full_content="Z" * 10_000)
    )
    resp = build_degraded_response(ctx, "error")
    assert "empty" not in resp.finding_refs            # blank finding dropped
    assert resp.finding_refs == ["big"]
    assert resp.text.count("Z") <= 4000                # per-finding body is capped
