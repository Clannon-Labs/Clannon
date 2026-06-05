import asyncio
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import tempfile
from typing import Callable

from foundation import SanitizationError, ThreatLevel

import bleach


@dataclass
class TextWorkerResult:
    name: str
    threat_level: ThreatLevel = ThreatLevel.NONE
    reason: str | None = None
    sanitized_text: str | None = None

    @property
    def passed(self) -> bool:
        return not self.threat_level.should_block


@dataclass
class TextScanResult:
    threat_level: ThreatLevel
    reason: str | None = None
    passed: bool = True
    sanitized_text: str | None = None


TextWorker = Callable[[str], TextWorkerResult]


@lru_cache(maxsize=1)
def _analyzer():
    from presidio_analyzer import AnalyzerEngine

    return AnalyzerEngine()


@lru_cache(maxsize=1)
def _anonymizer():
    from presidio_anonymizer import AnonymizerEngine

    return AnonymizerEngine()


def _normalize_text(text: str | bytes | bytearray | memoryview | object) -> str:
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
    results = _analyzer().analyze(text=text, language="en")
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


def _html_worker(text: str) -> TextWorkerResult:
    cleaned = bleach.clean(text, tags=[], attributes={}, strip=True)
    if cleaned == text:
        return TextWorkerResult(name="bleach")

    return TextWorkerResult(
        name="bleach",
        threat_level=ThreatLevel.LOW,
        reason="HTML content sanitized",
        sanitized_text=cleaned,
    )


def _highest_threat(results: list[TextWorkerResult]) -> ThreatLevel:
    if not results:
        return ThreatLevel.NONE

    order = {
        ThreatLevel.NONE: 0,
        ThreatLevel.LOW: 1,
        ThreatLevel.MEDIUM: 2,
        ThreatLevel.HIGH: 3,
        ThreatLevel.CRITICAL: 4,
    }
    return max((result.threat_level for result in results), key=order.__getitem__)


async def _run_worker(worker: TextWorker, text: str) -> TextWorkerResult:
    try:
        return await asyncio.to_thread(worker, text)
    except Exception as exc:
        worker_name = worker.__name__.removeprefix("_").removesuffix("_worker")
        raise SanitizationError(
            f"Text sanitizer worker failed: {exc}",
            modality="text",
            worker=worker_name,
        ) from exc


async def scan(text: str) -> TextScanResult:
    """
        It runs all the text sanitizer workers in parallel
        and returns the highest threat detected.
    """
    normalized_text = _normalize_text(text)
    results = await asyncio.gather(
        _run_worker(_secrets_worker, normalized_text),
        _run_worker(_pii_worker, normalized_text),
        _run_worker(_html_worker, normalized_text),
    )
    threat_level = _highest_threat(results)
    reasons = [result.reason for result in results if result.reason]
    sanitized_text = normalized_text

    pii_result = next((result for result in results if result.name == "presidio"), None)
    if pii_result and pii_result.sanitized_text:
        sanitized_text = pii_result.sanitized_text

    sanitized_text = bleach.clean(sanitized_text, tags=[], attributes={}, strip=True)
    if sanitized_text == normalized_text:
        sanitized_text = None

    return TextScanResult(
        threat_level=threat_level,
        reason="; ".join(reasons) if reasons else None,
        passed=not threat_level.should_block,
        sanitized_text=sanitized_text,
    )
