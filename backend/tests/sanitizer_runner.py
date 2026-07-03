import asyncio

import pytest

from foundation import BlockReason, Flow, ThreatLevel
from security.sanitizers import runner, pre_sanitization
from security.sanitizers.pre_sanitization import PreSanitizationResult
from security.sanitizers.workers import text, image, pdf, video, audio
from security.sanitizers.workers.text import TextScanResult


@pytest.fixture(autouse=True)
def _clean_pre_sanitization(monkeypatch):
    """Stub the ClamAV/YARA gate to pass so runner orchestration is isolated."""
    async def clean(raw):
        return PreSanitizationResult()
    monkeypatch.setattr(pre_sanitization, "run", clean)
    yield


def _flow(payload="some text", modalities=("text",)):
    flow = Flow.new(payload, "runner-test")
    flow.ctx.detected_modalities = list(modalities)
    return flow


def test_runner_blocks_on_high_worker(monkeypatch):
    async def high(raw):
        return TextScanResult(threat_level=ThreatLevel.HIGH, reason="secret detected", passed=False)
    monkeypatch.setattr(text, "scan", high)

    out = asyncio.run(runner.run(_flow()))

    assert out.status.value == "blocked"
    # Worker report is persisted on the block path (dead-letter parity).
    assert out.ctx.sanitization is not None


def test_runner_forwards_sanitized_payload(monkeypatch):
    async def clean(raw):
        return TextScanResult(threat_level=ThreatLevel.NONE, sanitized_text="cleaned")
    monkeypatch.setattr(text, "scan", clean)

    out = asyncio.run(runner.run(_flow(payload="dirty")))

    assert out.status.value == "ok"
    assert out.ctx.sanitization_blocked is False


def _spy_all_workers(monkeypatch):
    """Replace every modality worker's scan with a call recorder.

    Returns the list each invocation appends to, so a test can assert that no
    worker ran. The spy returns a clean result on purpose: if the pre-gate
    ordering ever regresses and a worker IS scheduled, the test fails on the
    empty-call assertion (a clear ordering signal) instead of crashing on an
    unexpected None inside the runner's gather loop.
    """
    invoked = []

    def make_spy(modality):
        async def spy(raw):
            invoked.append(modality)
            return TextScanResult(threat_level=ThreatLevel.NONE)
        return spy

    for modality, module in (
        ("text", text),
        ("image", image),
        ("pdf", pdf),
        ("video", video),
        ("audio", audio),
    ):
        monkeypatch.setattr(module, "scan", make_spy(modality))
    return invoked


@pytest.mark.parametrize("level", [ThreatLevel.HIGH, ThreatLevel.CRITICAL])
def test_pre_gate_block_skips_all_workers(monkeypatch, level):
    """A HIGH/CRITICAL pre-sanitization result blocks BEFORE any modality worker
    is scheduled.

    Pins the ordering guarantee in runner.run (the pre_result.should_block
    early-return precedes the worker task fan-out) and the NEVER line in
    security/sanitizers/CLAUDE.md: "Don't run a worker ahead of the pre-gate."
    The flow reports the pre-gate's own threat level and a malicious-content
    block, distinct from the worker-block path exercised above.
    """
    async def blocking(raw):
        return PreSanitizationResult(threat_level=level, reason="pre-gate hit", passed=False)
    monkeypatch.setattr(pre_sanitization, "run", blocking)

    # Every modality is "detected", so a worker WOULD be scheduled if the
    # pre-gate did not short-circuit first; this maximizes the ordering check.
    invoked = _spy_all_workers(monkeypatch)
    flow = _flow(modalities=("text", "image", "pdf", "video", "audio"))

    out = asyncio.run(runner.run(flow))

    assert out.status.value == "blocked"
    assert invoked == []                                    # no worker scan scheduled
    assert out.threat == level                              # pre-gate's level propagated
    assert out.reason == BlockReason.MALICIOUS_CONTENT.value
    assert out.ctx.sanitization_blocked is True
