"""
Upload admission — malware-scan a user-uploaded INPUT file at the boundary.

Policy (product decision): an uploaded input file (data to analyze, code to work
on) is scanned for GENUINELY malicious content — the same ClamAV/YARA pre-gate the
brief crosses — and either admitted with its ORIGINAL bytes intact or rejected. We
deliberately do NOT run the redacting modality workers (Presidio PII, etc.) on it:
the file is the user's own data and the expert needs it with full fidelity; the
no-network sandbox + the output filter contain residual risk.

Scope today: text-family files + PDF, decided by CONTENT sniff (libmagic), not by
extension. Fail-closed: if the malware gate cannot run (e.g. ClamAV unreachable),
the file is rejected, not admitted.

The server calls `scan_upload` per file; admitted files become `foundation.InputFile`
and ride on the context to be seeded into the expert's workspace.
"""

from __future__ import annotations

import os

import magic

from foundation import InputFile, SanitizationError, constants

from . import pre_sanitization

# same hard cap the brief gets; one upload may not exceed it
_MAX_UPLOAD_BYTES = constants.MAX_INPUT_SIZE_BYTES


def _safe_name(name: str) -> str:
    """Flatten an uploaded filename to a confined basename (no directories)."""
    base = os.path.basename(str(name or "").replace("\\", "/")).strip()
    return base or "upload"


def _admitted_modality(data: bytes) -> str | None:
    """Content-sniff the bytes: 'text' for the text family, 'pdf' for PDF, else
    None (out of scope for this cut). Mirrors intake's modality map."""
    try:
        mime = magic.from_buffer(data, mime=True)
    except Exception:  # noqa: BLE001 — undetectable type is just unsupported
        return None
    if mime.startswith("text/") or mime in constants.TEXTUAL_MIME_TYPES:
        return "text"
    if mime == "application/pdf":
        return "pdf"
    return None


async def scan_upload(name: str, data: bytes) -> tuple[InputFile | None, str | None]:
    """Scan one upload. Returns (InputFile, None) if admitted, or (None, reason) if
    rejected — empty, oversized, unsupported type, malicious, or unscannable."""
    safe = _safe_name(name)
    if not data:
        return None, f"{safe}: file is empty."
    if len(data) > _MAX_UPLOAD_BYTES:
        return None, f"{safe}: larger than the {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit."
    modality = _admitted_modality(data)
    if modality is None:
        return None, f"{safe}: unsupported file type — text-family files and PDF only for now."
    try:
        pre = await pre_sanitization.run(data)
    except SanitizationError:
        # fail-closed: a malware gate that cannot run does not admit the file
        return None, f"{safe}: could not be security-scanned, so it was not accepted."
    if pre.threat_level.should_block:
        return None, f"{safe}: rejected by the security scan ({pre.reason or 'malicious content'})."
    return InputFile(name=safe, modality=modality, data=data, size=len(data)), None
