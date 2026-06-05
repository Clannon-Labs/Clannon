"""
Small payload helpers for the normalizer layer.

These helpers are intentionally code-only and dependency-light. They keep
normalizer.py focused on stage decisions instead of byte/string coercion.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def payload_to_bytes(payload: Any) -> bytes:
    """Normalize bytes-like or file-path payloads into bytes."""
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, bytearray):
        return bytes(payload)
    if isinstance(payload, memoryview):
        return payload.tobytes()
    if isinstance(payload, (str, Path)):
        path = Path(payload)
        if path.exists() and path.is_file():
            return path.read_bytes()

    raise TypeError("payload cannot be read as bytes")


def payload_to_text(payload: Any) -> str:
    """Normalize text-like payloads into a Unicode string."""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="replace")
    if isinstance(payload, bytearray):
        return bytes(payload).decode("utf-8", errors="replace")
    if isinstance(payload, memoryview):
        return payload.tobytes().decode("utf-8", errors="replace")
    return str(payload)


def truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    """Return text capped to max_chars plus whether truncation happened."""
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True
