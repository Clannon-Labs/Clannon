"""
Upload admission — malware-scan a user-uploaded INPUT file at the boundary.

Policy (product decision): an uploaded input file (data to analyze, code to work
on) is scanned for GENUINELY malicious content — the same ClamAV/YARA pre-gate the
brief crosses — and either admitted with its ORIGINAL bytes intact or rejected. We
deliberately do NOT run the redacting modality workers (Presidio PII, etc.) on it:
the file is the user's own data and the expert needs it with full fidelity; the
no-network sandbox + the output filter contain residual risk.

Scope: text-family files + PDF + images + audio + video + zip archives, decided by
CONTENT sniff (libmagic), not by extension. Media (image/audio/video) is
malware-scanned then passed through INTACT — no metadata stripping, don't nerf the
media; the media expert reads it via a multimodal model. Fail-closed: if the malware
gate cannot run (e.g. ClamAV unreachable), the file is rejected, not admitted.

Archives (CB2 real-repo track, security review 2026-07-25): admitted the same way,
PLUS a Layer-1 decompression-bomb pre-check on the zip's own central directory
(entry count + declared uncompressed:compressed ratio) — metadata-only, no member is
ever decompressed here. This is a cheap pre-filter, not the authoritative guard:
declared sizes can be spoofed, so the real, byte-verified caps (and the per-member
malware scan) enforce again at extraction time in orchestration's `_seed_inputs`,
reading the SAME `settings.SECURITY.archive_*` floors. Rejecting the obviously-absurd
case here means a bomb never even gets admitted as an `InputFile` and re-attempted on
every expert call that seeds a workspace from it.

The server calls `scan_upload` per file; admitted files become `foundation.InputFile`
and ride on the context to be seeded into the expert's workspace.
"""

from __future__ import annotations

import io
import os
import zipfile

import magic

import settings
from foundation import InputFile, SanitizationError, constants

from . import pre_sanitization

# same hard cap the brief gets; one upload may not exceed it
_MAX_UPLOAD_BYTES = settings.INTAKE.max_input_size_bytes

# ZIP local-file-header / EOCD-only / spanned-archive signatures — checked directly
# rather than via libmagic: verified empirically that `magic.from_buffer()` (buffer
# mode) does NOT reliably recognize zip structure the way `magic.from_file()` does
# (zip detection needs to locate the End-Of-Central-Directory record, which libmagic's
# buffer-mode softmagic rules don't resolve here — reproduced on a real, valid zip:
# from_buffer -> "application/octet-stream"/"data", from_file -> correct "Zip archive
# data"). `zipfile.is_zipfile()` is the authoritative confirmation below — it IS the
# real parser, a stronger check than any magic-string guess.
_ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def _safe_name(name: str) -> str:
    """Flatten an uploaded filename to a confined basename (no directories)."""
    base = os.path.basename(str(name or "").replace("\\", "/")).strip()
    return base or "upload"


def _admitted_modality(data: bytes) -> str | None:
    """Content-sniff the bytes to a modality: 'text' for the text family, 'pdf' for
    PDF, 'image'/'audio'/'video' for media, 'archive' for a zip (CB2 real-repo track),
    else None (unsupported). Mirrors intake's modality map; the media expert reads
    image/audio/video/pdf via a multimodal model; an admitted archive is extracted into
    a workspace by orchestration's `_seed_inputs` (see module docstring)."""
    try:
        mime = magic.from_buffer(data, mime=True)
    except Exception:  # noqa: BLE001 — undetectable type is just unsupported
        return None
    if mime.startswith("text/") or mime in constants.TEXTUAL_MIME_TYPES:
        return "text"
    if mime == "application/pdf":
        return "pdf"
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("audio/"):
        return "audio"
    if mime.startswith("video/"):
        return "video"
    if data[:4] in _ZIP_SIGNATURES and zipfile.is_zipfile(io.BytesIO(data)):
        return "archive"
    return None


def _archive_bomb_precheck(data: bytes) -> str | None:
    """Layer-1 decompression-bomb guard (security review 2026-07-25 — see module
    docstring): metadata-only, reads the zip's own central directory without
    decompressing any member. Returns a rejection reason, or None if it passes.

    A cheap PRE-filter, not the authoritative guard — a zip's declared per-entry
    sizes can be spoofed, so this only refuses the obviously-absurd case before
    admission; the real, byte-verified caps re-enforce at extraction time against
    the SAME `settings.SECURITY.archive_*` floors (orchestration's `_seed_inputs`).
    Entry-count parsing itself is implicitly bounded by `_MAX_UPLOAD_BYTES`, already
    checked before this runs — a central directory can't list more entries than fit
    in an already-capped file."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
    except zipfile.BadZipFile:
        return "corrupt or invalid zip archive"

    entries = len(infos)
    if entries > settings.SECURITY.archive_max_entries:
        return f"archive has {entries} entries (max {settings.SECURITY.archive_max_entries})"

    total_uncompressed = sum(info.file_size for info in infos)
    ratio_cap = settings.SECURITY.archive_max_uncompressed_ratio
    # Ratio against the archive's OWN compressed byte length (not a fixed byte total) —
    # self-adjusts to whatever the separate archive-upload size cap ends up being,
    # and IS the standard zip-bomb heuristic (a legitimate repo rarely compresses
    # better than single-digit ratios; 42.zip-style bombs hit the thousands).
    if total_uncompressed > ratio_cap * max(len(data), 1):
        return (
            f"archive expands to {total_uncompressed} bytes from {len(data)} compressed "
            f"(ratio exceeds the {ratio_cap}x limit)"
        )
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
        return None, (
            f"{safe}: unsupported file type — text-family files, PDF, images, audio, "
            "video, and zip archives only."
        )
    try:
        pre = await pre_sanitization.run(data)
    except SanitizationError:
        # fail-closed: a malware gate that cannot run does not admit the file
        return None, f"{safe}: could not be security-scanned, so it was not accepted."
    if pre.threat_level.should_block:
        return None, f"{safe}: rejected by the security scan ({pre.reason or 'malicious content'})."
    if modality == "archive":
        bomb_reason = _archive_bomb_precheck(data)
        if bomb_reason is not None:
            return None, f"{safe}: rejected ({bomb_reason})."
    return InputFile(name=safe, modality=modality, data=data, size=len(data)), None
