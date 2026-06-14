import asyncio

import pytest

from foundation import Flow, ThreatLevel
from security.sanitizers import runner, pre_sanitization
from security.sanitizers.pre_sanitization import PreSanitizationResult
from security.sanitizers.workers import text
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
