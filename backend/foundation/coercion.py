"""
Shared payload coercion primitive.

Stages receive payloads in a few shapes — bytes-like buffers, an explicit
filesystem path, or text. This module is the single, auditable place that
decides how each shape becomes bytes, so the security-critical rule lives in one
spot instead of being re-implemented per worker.

Security boundary:
    A ``str`` is ALWAYS literal text and is encoded as UTF-8. It is never
    interpreted as a filesystem path. Only an explicit ``os.PathLike`` from a
    trusted caller is read from disk. User-supplied content arrives as ``str``,
    so this guarantees user input can never be probed against the server's
    filesystem (no arbitrary-file-read).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def coerce_to_bytes(payload: Any) -> bytes:
    """
    Coerce a pipeline payload into bytes.

    Rules:
        bytes / bytearray / memoryview -> those bytes, unchanged
        os.PathLike                    -> file contents (trusted callers only)
        str                            -> UTF-8 encoded text (never a path)

    Raises:
        TypeError: when the payload is none of the supported shapes. Callers
            that need a domain-specific error (e.g. SanitizationError) should
            catch this and wrap it.
    """
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, bytearray):
        return bytes(payload)
    if isinstance(payload, memoryview):
        return payload.tobytes()
    if isinstance(payload, str):
        return payload.encode("utf-8", errors="replace")
    if isinstance(payload, os.PathLike):
        return Path(payload).read_bytes()
    raise TypeError(f"payload cannot be read as bytes: {type(payload).__name__}")
