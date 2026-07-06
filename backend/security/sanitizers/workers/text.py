"""
Text sanitizer worker.

This module runs the text-specific sanitizer checks after the universal
pre-sanitization gate has already scanned the raw payload. The worker performs
two independent checks:

* detect-secrets flags credentials/tokens and blocks high-risk input.
* Presidio detects PII and produces anonymized text.

HTML/markup is intentionally NOT stripped or escaped here. The text sink is an
LLM, not a browser DOM, so HTML carries no injection risk at this stage, while
escaping bare ``<``/``>``/``&`` would silently corrupt ordinary text and code
(e.g. ``vector<int>`` or ``a < b``). XSS protection belongs to the output
filter when content is rendered in the dashboard, not to input sanitization.

scan() returns a TextScanResult for the runner; sanitized_text is the text
worker's safe replacement payload for later stages.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import tempfile
from typing import Callable
import asyncio

import settings
from foundation import ThreatLevel

from ._base import highest_threat, run_subworker


@dataclass
class TextWorkerResult:
    """Internal result returned by one text sub-worker."""
    name: str
    threat_level: ThreatLevel = ThreatLevel.NONE
    reason: str | None = None
    sanitized_text: str | None = None

    @property
    def passed(self) -> bool:
        return not self.threat_level.should_block


@dataclass
class TextScanResult:
    """Public result returned to security/sanitizers/runner.py."""
    threat_level: ThreatLevel
    reason: str | None = None
    passed: bool = True
    sanitized_text: str | None = None


TextWorker = Callable[[str], TextWorkerResult]

# Entities Presidio is allowed to redact. Hard identifiers only: contact,
# financial, government-ID, and network identifiers. Deliberately excludes
# PERSON / LOCATION / DATE_TIME / NRP / URL, those are the subject matter of
# research queries ("the capital of France", "papers by Hinton since 2020"),
# and redacting them destroys the request before the orchestrator sees it.
# Sourced from config/backend/security.yaml (settings.SECURITY, docket D8) — the
# floor there is this same baseline; config may only ADD entities, never drop one.
PII_REDACTED_ENTITIES = settings.SECURITY.pii_redacted_entities


@lru_cache(maxsize=1)
def _analyzer():
    """Create Presidio's analyzer lazily because initialization is expensive."""
    from presidio_analyzer import AnalyzerEngine

    return AnalyzerEngine()


@lru_cache(maxsize=1)
def _anonymizer():
    """Create Presidio's anonymizer lazily and reuse it between scans."""
    from presidio_anonymizer import AnonymizerEngine

    return AnonymizerEngine()


def warm() -> bool:
    """Build the Presidio engines now (they are expensive on first use) so the first
    real input isn't slowed by their cold start. Best-effort; the lazy getters still
    build them on demand if warmup is skipped. Returns True if both are ready."""
    try:
        _analyzer()
        _anonymizer()
        return True
    except Exception:  # noqa: BLE001 — warmup never fails a run
        return False


def _normalize_text(text: str | bytes | bytearray | memoryview | object) -> str:
    """Convert supported text-like payloads into a Unicode string."""
    if isinstance(text, str):
        return text
    if isinstance(text, bytes):
        return text.decode("utf-8", errors="replace")
    if isinstance(text, bytearray):
        return bytes(text).decode("utf-8", errors="replace")
    if isinstance(text, memoryview):
        return text.tobytes().decode("utf-8", errors="replace")
    return str(text)


def _pii_worker(text: str) -> TextWorkerResult:
    """
    Detect personally identifiable information and anonymize it.

    PII is marked MEDIUM because it is sensitive but not always malicious; the
    pipeline can continue with sanitized_text when no higher-risk worker blocks.
    """
    results = _analyzer().analyze(
        text=text, language="en", entities=PII_REDACTED_ENTITIES
    )
    if not results:
        return TextWorkerResult(name="presidio")

    anonymized = _anonymizer().anonymize(text=text, analyzer_results=results).text
    entity_types = sorted({result.entity_type for result in results})

    return TextWorkerResult(
        name="presidio",
        threat_level=ThreatLevel.MEDIUM,
        reason=f"PII detected: {', '.join(entity_types)}",
        sanitized_text=anonymized,
    )


def _secrets_worker(text: str) -> TextWorkerResult:
    """
    Detect API keys, tokens, and credentials with detect-secrets.

    detect-secrets scans files, so the text is written to a temporary file. A
    finding is HIGH because secrets should not be forwarded into LLM/tool layers.
    """
    from detect_secrets import SecretsCollection
    from detect_secrets.settings import default_settings

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / "text-sanitizer-input.txt"
        tmp_path.write_text(text, encoding="utf-8")

        with default_settings():
            secrets = SecretsCollection()
            secrets.scan_file(str(tmp_path))

    findings = [
        getattr(secret, "type", "secret")
        for file_findings in secrets.data.values()
        for secret in file_findings
    ]

    if not findings:
        return TextWorkerResult(name="detect-secrets")

    return TextWorkerResult(
        name="detect-secrets",
        threat_level=ThreatLevel.HIGH,
        reason=f"Secret detected: {', '.join(sorted(set(findings)))}",
    )


def _scan_sync(text: str) -> TextScanResult:
    """
    Run all text sanitizer sub-workers and aggregate their results synchronously.

    This function contains the real sanitizer logic. scan() is intentionally
    only the async entry point that moves this blocking work to a thread. The
    sub-workers inspect the same original text independently. Sanitized text is
    the Presidio-anonymized result when PII was found, otherwise None (no
    safe-replacement payload is needed).
    """
    normalized_text = _normalize_text(text)
    results = [
        run_subworker(_secrets_worker, normalized_text, modality="text", label="Text"),
        run_subworker(_pii_worker, normalized_text, modality="text", label="Text"),
    ]
    threat_level = highest_threat(results)
    reasons = [result.reason for result in results if result.reason]
    sanitized_text = None

    pii_result = next((result for result in results if result.name == "presidio"), None)
    if pii_result and pii_result.sanitized_text:
        sanitized_text = pii_result.sanitized_text

    return TextScanResult(
        threat_level=threat_level,
        reason="; ".join(reasons) if reasons else None,
        passed=not threat_level.should_block,
        sanitized_text=sanitized_text,
    )

async def scan(text: str) -> TextScanResult:
    """
    Async entry point used by the sanitizer runner.

    Text scanning uses libraries that do blocking CPU/file work, so the full
    synchronous scan is offloaded to a thread. This keeps the event loop free
    while the runner executes modality workers concurrently.
    """
    return await asyncio.to_thread(_scan_sync, text)
