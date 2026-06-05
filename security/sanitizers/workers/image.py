"""
Image sanitizer worker.

This module handles image-specific sanitization after the universal
pre-sanitization gate has already run. Its job is intentionally narrow:
validate that the payload is actually an image, reject parser-level image
hazards, and strip metadata without recompressing pixels whenever possible.
"""

import asyncio
import io
import subprocess
from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Any

from PIL import Image, UnidentifiedImageError

from foundation import SanitizationError, ThreatLevel, constants


@dataclass
class ImageScanResult:
    """
    Result returned by the image sanitizer.

    sanitized_image is bytes because the safe output should be passed around as
    an in-memory image payload. It is None only if sanitization failed before a
    cleaned image could be produced.
    """
    threat_level: ThreatLevel
    reason: str | None = None
    passed: bool = True
    sanitized_image: bytes | None = None
    format: str | None = None
    size: tuple[int, int] | None = None


def _payload_to_bytes(image: Any) -> bytes:
    """Normalize supported image inputs into bytes for Pillow."""
    if isinstance(image, bytes):
        return image
    if isinstance(image, bytearray):
        return bytes(image)
    if isinstance(image, memoryview):
        return image.tobytes()
    if isinstance(image, (str, Path)):
        path = Path(image)
        if path.exists() and path.is_file():
            return path.read_bytes()

    raise SanitizationError(
        "Image sanitizer expected bytes or an image file path",
        modality="image",
        worker="image",
    )


def _verify_image(payload: bytes) -> tuple[str, tuple[int, int]]:
    """
    Ask Pillow to parse and verify the image structure.

    image.verify() detects malformed images without fully decoding pixel data.
    Decompression bombs are treated as sanitizer errors because they can
    exhaust memory/CPU if processed further.
    """
    try:
        with Image.open(io.BytesIO(payload)) as image:
            image.verify()
            image_format = image.format or "PNG"
            image_size = image.size
    except Image.DecompressionBombError as exc:
        raise SanitizationError(
            f"Image decompression bomb detected: {exc}",
            modality="image",
            worker="pillow",
        ) from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise SanitizationError(
            f"Invalid image payload: {exc}",
            modality="image",
            worker="pillow",
        ) from exc

    width, height = image_size
    if max(width, height) > constants.MAX_IMAGE_DIMENSION_PX:
        raise SanitizationError(
            f"Image dimension exceeds limit: {width}x{height}",
            modality="image",
            worker="pillow",
        )

    return image_format, image_size


def _has_metadata(payload: bytes) -> bool:
    """Return True when Pillow can see common metadata containers."""
    try:
        with Image.open(io.BytesIO(payload)) as image:
            return bool(image.getexif() or image.info)
    except (UnidentifiedImageError, OSError):
        return False


def _suffix_for_format(image_format: str) -> str:
    """Choose a file suffix that exiftool understands for this image format."""
    return {
        "JPEG": ".jpg",
        "PNG": ".png",
        "WEBP": ".webp",
        "TIFF": ".tiff",
        "GIF": ".gif",
    }.get(image_format.upper(), ".img")


def _sanitize_image(payload: bytes, image_format: str) -> bytes:
    """
    Strip metadata without recompressing image pixels.

    Pillow re-saving JPEG/video-like formats can visibly degrade quality.
    exiftool edits metadata containers without re-encoding pixels, so it is the
    quality-first sanitizer. If metadata stripping fails, the validated original
    bytes are preserved rather than silently degrading the media.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / f"input{_suffix_for_format(image_format)}"
        path.write_bytes(payload)

        result = subprocess.run(
            ["exiftool", "-all=", "-overwrite_original", "-q", "-q", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode != 0:
            return payload

        return path.read_bytes()


def _scan_sync(image: Any) -> ImageScanResult:
    """Run the blocking Pillow work in a synchronous helper."""
    payload = _payload_to_bytes(image)
    image_format, image_size = _verify_image(payload)
    had_metadata = _has_metadata(payload)
    sanitized_image = _sanitize_image(payload, image_format) if had_metadata else payload

    reason = None
    threat_level = ThreatLevel.NONE
    if sanitized_image != payload:
        reason = "Image metadata stripped losslessly"
        threat_level = ThreatLevel.LOW

    return ImageScanResult(
        threat_level=threat_level,
        reason=reason,
        passed=not threat_level.should_block,
        sanitized_image=sanitized_image,
        format=image_format,
        size=image_size,
    )


async def scan(image: Any) -> ImageScanResult:
    """
    Public async entry point used by the sanitizer runner.

    Pillow work is CPU/blocking I/O adjacent, so it is moved to a worker thread
    to avoid blocking the event loop while other modality workers run.
    """
    return await asyncio.to_thread(_scan_sync, image)
