"""
Universal pre-sanitization gate.

This module runs before every modality-specific sanitizer worker. It scans the
raw payload exactly as received from intake so malware/signature threats are
blocked before text, image, PDF, audio, or video workers spend time parsing the
content.

Two engines are used:

* ClamAV, via the clamd Python client and a running clamd daemon.
* YARA, via yara-python and local .yar/.yara rule files.

The public run()/scan() function returns a PreSanitizationResult. A blocking
result should stop the sanitizer runner before any other workers are scheduled.
"""

from __future__ import annotations

import asyncio
import io
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import clamd
import yara

from foundation import SanitizationError, ThreatLevel


CLAMAV_HOST = os.getenv("CLAMAV_HOST", "127.0.0.1")
CLAMAV_PORT = int(os.getenv("CLAMAV_PORT", "3310"))
YARA_RULES_DIR = os.getenv("AGENT_YARA_DIR", "rules")


@dataclass(slots=True)
class EngineScanResult:
    """Result from one pre-sanitization engine, such as ClamAV or YARA."""
    engine: str
    threat_level: ThreatLevel
    reason: str | None = None
    signature: str | None = None
    skipped: bool = False

    @property
    def passed(self) -> bool:
        return not self.threat_level.should_block


@dataclass(slots=True)
class PreSanitizationResult:
    """Aggregate result returned to the sanitizer runner."""
    threat_level: ThreatLevel = ThreatLevel.NONE
    reason: str | None = None
    passed: bool = True
    engine_results: list[EngineScanResult] = field(default_factory=list)


def _payload_to_bytes(raw: Any) -> bytes:
    """
    Convert raw pipeline payloads into bytes for binary scanners.

    A str payload is always literal user text and is encoded as UTF-8 — it is
    never interpreted as a filesystem path, so user content cannot be probed
    against the disk. File inputs reach the pipeline as os.PathLike from a
    trusted caller.
    """
    if isinstance(raw, bytes):
        return raw
    if isinstance(raw, bytearray):
        return bytes(raw)
    if isinstance(raw, memoryview):
        return raw.tobytes()
    if isinstance(raw, str):
        return raw.encode("utf-8", errors="replace")
    if isinstance(raw, os.PathLike):
        return Path(raw).read_bytes()
    return repr(raw).encode("utf-8", errors="replace")


class ClamScanner:
    """ClamAV scanner using clamd's TCP INSTREAM protocol."""
    def __init__(
        self,
        host: str = CLAMAV_HOST,
        port: int = CLAMAV_PORT,
        timeout_s: float = 10.0,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout_s = timeout_s

    async def scan(self, raw: Any) -> EngineScanResult:
        """Normalize the payload and run the blocking clamd scan in a thread."""
        payload = _payload_to_bytes(raw)
        return await asyncio.to_thread(self._scan_sync, payload)

    def _scan_sync(self, payload: bytes) -> EngineScanResult:
        """
        Send bytes to clamd and translate its response into EngineScanResult.

        The ClamAV daemon must be reachable at CLAMAV_HOST:CLAMAV_PORT. A
        connection failure is a sanitizer failure rather than a clean result.
        """
        try:
            client = clamd.ClamdNetworkSocket(
                host=self.host,
                port=self.port,
                timeout=self.timeout_s,
            )
            response = client.instream(io.BytesIO(payload))
        except clamd.ClamdError as exc:
            raise SanitizationError(
                f"ClamAV scan failed: {exc}",
                modality="all",
                worker="clamav",
            ) from exc

        status, signature = response.get("stream", ("ERROR", None))
        if status == "OK":
            return EngineScanResult(engine="clamav", threat_level=ThreatLevel.NONE)

        if status == "FOUND":
            return EngineScanResult(
                engine="clamav",
                threat_level=ThreatLevel.HIGH,
                reason=f"ClamAV detected malware signature: {signature}",
                signature=str(signature),
            )

        raise SanitizationError(
            f"ClamAV returned an unexpected response: {response}",
            modality="all",
            worker="clamav",
        )


class YaraScanner:
    """YARA scanner that compiles .yar/.yara files from a rules directory."""
    def __init__(self, rules_dir: str | Path = YARA_RULES_DIR) -> None:
        self.rules_dir = Path(rules_dir)
        self.rules_dir.mkdir(parents=True, exist_ok=True)

    async def scan(self, raw: Any) -> EngineScanResult:
        """Normalize the payload and run the blocking YARA scan in a thread."""
        payload = _payload_to_bytes(raw)
        return await asyncio.to_thread(self._scan_sync, payload)

    def _scan_sync(self, payload: bytes) -> EngineScanResult:
        """
        Compile available YARA rules and match them against the payload.

        Missing rules are reported as skipped/clean so local development can run
        before rules are added. Invalid rules raise SanitizationError.
        """
        rule_files = self._rule_files()
        if not rule_files:
            return EngineScanResult(
                engine="yara",
                threat_level=ThreatLevel.NONE,
                reason=f"No YARA rules found in {self.rules_dir}",
                skipped=True,
            )

        try:
            rules = yara.compile(
                filepaths={str(index): str(path) for index, path in enumerate(rule_files)}
            )
            matches = rules.match(data=payload)
        except Exception as exc:
            raise SanitizationError(
                f"YARA scan failed: {exc}",
                modality="all",
                worker="yara",
            ) from exc

        if not matches:
            return EngineScanResult(engine="yara", threat_level=ThreatLevel.NONE)

        signature = ", ".join(match.rule for match in matches)
        return EngineScanResult(
            engine="yara",
            threat_level=ThreatLevel.HIGH,
            reason=f"YARA matched threat rule(s): {signature}",
            signature=signature,
        )

    def _rule_files(self) -> list[Path]:
        """Return all YARA rule files below the configured rules directory."""
        if not self.rules_dir.exists():
            return []
        return sorted(
            path
            for path in self.rules_dir.rglob("*")
            if path.suffix.lower() in {".yar", ".yara"} and path.is_file()
        )


async def scan(raw: Any) -> PreSanitizationResult:
    """
    Run all universal pre-sanitization engines in order.

    ClamAV runs before YARA because antivirus signatures are a cheap and broad
    malware gate. The function returns the first blocking engine result while
    preserving engine details collected up to that point.
    """
    engine_results = [
        await ClamScanner().scan(raw),
        await YaraScanner().scan(raw),
    ]

    for result in engine_results:
        if result.threat_level.should_block:
            return PreSanitizationResult(
                threat_level=result.threat_level,
                reason=result.reason,
                passed=False,
                engine_results=engine_results,
            )

    return PreSanitizationResult(engine_results=engine_results)


async def run(raw: Any) -> PreSanitizationResult:
    """Alias used by the sanitizer runner."""
    return await scan(raw)
