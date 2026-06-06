"""
Intake stage — the first raw-input admission gate.

Intake is deliberately cheap: rate-limit, size-check, and detect the input
modality before any sanitizer, normalizer, or LLM does work. It performs no deep
security analysis — it only decides what the payload is and whether it may enter
the sanitizer layer.

Trust boundary: a ``str`` payload is always literal user text and is never
interpreted as a filesystem path. Only an explicit ``os.PathLike`` from a
trusted caller is treated as a file (see foundation.coerce_to_bytes).
"""

import os
import time
import magic
from pathlib import Path

from foundation import Flow, Origin, BlockReason, ThreatLevel
from foundation import Modality, constants, PipelineStage
from foundation import (
    InputError,
    UnsupportedModalityError,
    MalformedInputError,
)
from .rate_limiter import check_request_rate


def _input_size_bytes(payload) -> int:
    """
    Return the byte size of a supported payload shape.

    A str is measured as UTF-8 encoded bytes (it is text, never a path). Unknown
    types raise MalformedInputError so they are blocked as bad input, not failed
    as an infrastructure fault.
    """
    if isinstance(payload, str):
        return len(payload.encode("utf-8", errors="replace"))
    if isinstance(payload, (bytes, bytearray, memoryview)):
        return len(payload)
    if isinstance(payload, os.PathLike):
        try:
            return Path(payload).stat().st_size
        except OSError as exc:
            raise MalformedInputError("could not read input file", cause=exc)
    raise MalformedInputError(f"cannot determine size of input type: {type(payload).__name__}")


def _modality_from_mime(mime: str) -> Modality | None:
    """Map a detected MIME type to a supported Modality, or None if unsupported."""
    if mime.startswith("text/") or mime in constants.TEXTUAL_MIME_TYPES:
        return Modality.TEXT
    if mime == "application/pdf":
        return Modality.PDF
    if mime.startswith("image/"):
        return Modality.IMAGE
    if mime.startswith("audio/"):
        return Modality.AUDIO
    if mime.startswith("video/"):
        return Modality.VIDEO
    return None


def _detect_modality(payload) -> Modality:
    """
    Detect the input modality.

    A str payload is always literal user text, so it maps directly to TEXT with
    no content sniffing (this also stops structured text like JSON from being
    misclassified). Binary uploads are content-sniffed with libmagic; file
    inputs arrive as os.PathLike from a trusted caller.
    """
    if isinstance(payload, str):
        return Modality.TEXT

    try:
        if isinstance(payload, os.PathLike):
            mime = magic.from_file(os.fspath(payload), mime=True)
        else:
            if isinstance(payload, bytearray):
                payload = bytes(payload)
            elif isinstance(payload, memoryview):
                payload = payload.tobytes()
            mime = magic.from_buffer(payload, mime=True)
    except Exception as exc:
        raise MalformedInputError("could not detect mime type", cause=exc)

    modality = _modality_from_mime(mime)
    if modality is None:
        raise UnsupportedModalityError(f"unsupported modality {mime}")
    return modality


async def process(flow: Flow) -> Flow:
    started = time.monotonic()

    try:
        raw_input = await flow.load()  # payload in its current condition

        rate_limit = check_request_rate(flow.ctx.session_id)
        if not rate_limit.allowed:
            return flow.block(BlockReason.RATE_LIMITED, ThreatLevel.NONE, Origin.INTAKE, started)

        # TODO(HTTP): enforce streaming/Content-Length caps at the HTTP boundary
        # before the payload is fully buffered into memory. This in-process check
        # is the backstop, not the first line of defense.
        size = _input_size_bytes(raw_input)
        if size == 0:
            return flow.block(BlockReason.MALFORMED_INPUT, ThreatLevel.NONE, Origin.INTAKE, started)
        if size > constants.MAX_INPUT_SIZE_BYTES:
            return flow.block(BlockReason.INPUT_TOO_LARGE, ThreatLevel.NONE, Origin.INTAKE, started)

        modality = _detect_modality(raw_input)

        flow.ctx.raw_input = raw_input
        # Only the primary modality is processed today. detected_modalities stays
        # a list so multi-modality fan-out (e.g. a PDF with embedded images) can
        # be added later without changing this contract.
        # TODO(orchestrator): fan out per modality; see normalizer._primary_modality.
        flow.ctx.detected_modalities = [modality.value]
        flow.ctx.advance(PipelineStage.INTAKE)

        # Forward to the next stage. A new Flow is created carrying the same ctx.
        return flow.next(raw_input, Origin.INTAKE, started)

    except UnsupportedModalityError:
        # A modality we don't handle is a user/request problem, not a threat.
        return flow.block(BlockReason.UNSUPPORTED_MODALITY, ThreatLevel.NONE, Origin.INTAKE, started)

    except InputError:
        # Expected bad input (malformed, unknown type, unreadable file) — block,
        # not fail. These are request problems, not infrastructure faults.
        return flow.block(BlockReason.MALFORMED_INPUT, ThreatLevel.NONE, Origin.INTAKE, started)

    except Exception as exc:
        return flow.fail(exc, Origin.INTAKE, started)
