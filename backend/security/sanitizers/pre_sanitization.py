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
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import clamd
import yara

from foundation import SanitizationError, ThreatLevel, coerce_to_bytes, constants


CLAMAV_HOST = os.getenv("CLAMAV_HOST", "127.0.0.1")
CLAMAV_PORT = int(os.getenv("CLAMAV_PORT", "3310"))
YARA_RULES_DIR = os.getenv("AGENT_YARA_DIR", "rules")

# When YARA rules are required, a missing/empty rules dir is a hard config fault
# (fail-closed) rather than a silent skip. Enabled in production or explicitly.
YARA_REQUIRED = (
    os.getenv("VRAKSHA_ENV", "").strip().lower() in {"prod", "production"}
    or os.getenv("AGENT_REQUIRE_YARA", "").strip().lower() in {"1", "true", "yes"}
)


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
        payload = coerce_to_bytes(raw)
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
    """
    YARA scanner that compiles .yar/.yara files from a rules directory.

    Compiled rules are cached and only recompiled when the rule files change
    (path or mtime), so the expensive yara.compile() does not run on every
    request. A module-level singleton (_yara_scanner) shares this cache.
    """
    def __init__(self, rules_dir: str | Path = YARA_RULES_DIR) -> None:
        self.rules_dir = Path(rules_dir)
        self.rules_dir.mkdir(parents=True, exist_ok=True)
        self._compiled: yara.Rules | None = None
        self._compiled_signature: tuple | None = None
        self._compile_lock = threading.Lock()

    async def scan(self, raw: Any) -> EngineScanResult:
        """Normalize the payload and run the blocking YARA scan in a thread."""
        payload = coerce_to_bytes(raw)
        return await asyncio.to_thread(self._scan_sync, payload)

    def _rules_signature(self, rule_files: list[Path]) -> tuple:
        """Identity of the current rule set: (path, mtime) per file."""
        return tuple((str(path), path.stat().st_mtime) for path in rule_files)

    def _load_rules(self, rule_files: list[Path]) -> yara.Rules:
        """Compile rules once and reuse until the rule files change."""
        signature = self._rules_signature(rule_files)
        with self._compile_lock:
            if self._compiled is not None and signature == self._compiled_signature:
                return self._compiled
            compiled = yara.compile(
                filepaths={str(index): str(path) for index, path in enumerate(rule_files)}
            )
            self._compiled = compiled
            self._compiled_signature = signature
            return compiled

    def _scan_sync(self, payload: bytes) -> EngineScanResult:
        """
        Match cached/compiled YARA rules against the payload.

        Missing rules are reported as skipped/clean in development so the
        pipeline runs before rules are added; when YARA_REQUIRED (production),
        a missing rule set is a hard SanitizationError (fail-closed). Invalid
        rules always raise SanitizationError.
        """
        rule_files = self._rule_files()
        if not rule_files:
            if YARA_REQUIRED:
                raise SanitizationError(
                    f"YARA rules required but none found in {self.rules_dir}",
                    modality="all",
                    worker="yara",
                )
            return EngineScanResult(
                engine="yara",
                threat_level=ThreatLevel.NONE,
                reason=f"No YARA rules found in {self.rules_dir}",
                skipped=True,
            )

        try:
            rules = self._load_rules(rule_files)
            # the engine-level timeout matters: asyncio cancellation stops the
            # await, not the scanning thread — without it a pathological
            # rule x payload combination pins a worker thread forever
            matches = rules.match(data=payload, timeout=int(constants.SANITIZER_TIMEOUT_WORKER_S))
        except SanitizationError:
            raise
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


# Shared singletons: reused across requests so the YARA rule cache persists and
# scanner objects are not rebuilt per request.
_clam_scanner = ClamScanner()
_yara_scanner = YaraScanner()


async def scan(raw: Any) -> PreSanitizationResult:
    """
    Run the universal pre-sanitization engines concurrently.

    ClamAV (broad signature AV) and YARA (custom rules) are independent, so they
    run in parallel on the same bytes. The payload is coerced once and shared.
    Any blocking engine result fails the gate; an engine fault propagates as a
    SanitizationError (fail-closed).
    """
    payload = coerce_to_bytes(raw)
    engine_results = list(
        await asyncio.gather(
            asyncio.to_thread(_clam_scanner._scan_sync, payload),
            asyncio.to_thread(_yara_scanner._scan_sync, payload),
        )
    )

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
