"""
Small payload helpers for the normalizer layer.

These helpers are intentionally code-only and dependency-light. They keep
normalizer.py focused on stage decisions instead of byte/string coercion.
"""

from __future__ import annotations

import os
import unicodedata
from pathlib import Path
from typing import Any


# Format (category Cf) characters that carry real linguistic/emoji meaning and
# must survive normalization: zero-width non-joiner and zero-width joiner.
_ALLOWED_FORMAT_CHARS = {chr(0x200C), chr(0x200D)}  # ZWNJ, ZWJ


def stabilize_unicode(text: str) -> str:
    """
    Canonicalize text to NFKC and drop invisible format/bidi characters.

    NFKC folds confusable and full-width forms so deterministic downstream
    scans (verifier injection rules, secret/PII patterns) see one canonical
    representation. Zero-width and bidi-control characters (category ``Cf``)
    are removed because they can split tokens to evade those `\\b`-anchored
    scans (and bidi overrides enable Trojan-Source style attacks). ZWNJ/ZWJ are
    preserved so emoji sequences and complex scripts are not corrupted.
    """
    normalized = unicodedata.normalize("NFKC", text)
    return "".join(
        char
        for char in normalized
        if unicodedata.category(char) != "Cf" or char in _ALLOWED_FORMAT_CHARS
    )


def payload_to_bytes(payload: Any) -> bytes:
    """
    Normalize bytes-like or explicit file-path payloads into bytes.

    A str is never treated as a filesystem path: user content must not be
    probed against the disk. Binary inputs reach this helper either as bytes
    (the normal pipeline path) or as os.PathLike from a trusted caller.
    """
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, bytearray):
        return bytes(payload)
    if isinstance(payload, memoryview):
        return payload.tobytes()
    if isinstance(payload, os.PathLike):
        return Path(payload).read_bytes()

    raise TypeError("payload cannot be read as bytes")


def payload_to_text(payload: Any) -> str:
    """Decode text-like payloads and return a stable, canonical Unicode string."""
    if isinstance(payload, str):
        text = payload
    elif isinstance(payload, bytes):
        text = payload.decode("utf-8", errors="replace")
    elif isinstance(payload, bytearray):
        text = bytes(payload).decode("utf-8", errors="replace")
    elif isinstance(payload, memoryview):
        text = payload.tobytes().decode("utf-8", errors="replace")
    else:
        text = str(payload)
    return stabilize_unicode(text)


def truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    """Return text capped to max_chars plus whether truncation happened."""
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True
