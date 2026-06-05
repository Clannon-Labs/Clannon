"""
Video sanitizer worker.

This module runs after universal pre-sanitization has already scanned the raw
payload with ClamAV/YARA. Video sanitization focuses on parser safety, resource
limits, metadata stripping, and producing a quality-preserving payload for later
pipeline stages.

The worker uses ffmpeg/ffprobe, through ffmpeg-python, to validate, inspect, and
remux video. scan() is only the async entry point; _scan_sync() contains the
real blocking work and is offloaded to a thread.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Any, Callable

import ffmpeg

from foundation import SanitizationError, ThreatLevel, constants


@dataclass
class VideoWorkerResult:
    """Internal result returned by one video sub-worker."""
    name: str
    threat_level: ThreatLevel = ThreatLevel.NONE
    reason: str | None = None
    sanitized_video: bytes | None = None
    duration_s: float | None = None
    format: str | None = None
    metadata_keys: list[str] | None = None
    resolution: tuple[int, int] | None = None

    @property
    def passed(self) -> bool:
        return not self.threat_level.should_block


@dataclass
class VideoScanResult:
    """Public result returned to security/sanitizers/runner.py."""
    threat_level: ThreatLevel
    reason: str | None = None
    passed: bool = True
    sanitized_video: bytes | None = None
    duration_s: float | None = None
    format: str | None = None
    metadata_keys: list[str] | None = None
    resolution: tuple[int, int] | None = None


VideoWorker = Callable[[Path], VideoWorkerResult]


def _payload_to_bytes(video: Any) -> bytes:
    """Normalize supported video inputs into bytes."""
    if isinstance(video, bytes):
        return video
    if isinstance(video, bytearray):
        return bytes(video)
    if isinstance(video, memoryview):
        return video.tobytes()
    if isinstance(video, (str, Path)):
        path = Path(video)
        if path.exists() and path.is_file():
            return path.read_bytes()

    raise SanitizationError(
        "Video sanitizer expected bytes or a video file path",
        modality="video",
        worker="video",
    )


def _ffmpeg_error_message(exc: ffmpeg.Error) -> str:
    """Return a readable ffmpeg/ffprobe error message."""
    stderr = getattr(exc, "stderr", None)
    if isinstance(stderr, bytes):
        return stderr.decode("utf-8", errors="replace").strip()
    if stderr:
        return str(stderr)
    return str(exc)


def _duration_from_probe(
    format_info: dict[str, Any],
    video_streams: list[dict[str, Any]],
) -> float | None:
    """Extract duration from ffprobe format data or the first video stream."""
    candidates = [format_info.get("duration")]
    candidates.extend(stream.get("duration") for stream in video_streams)

    for candidate in candidates:
        if candidate is None:
            continue
        try:
            return float(candidate)
        except (TypeError, ValueError):
            continue
    return None


def _probe_worker(path: Path) -> VideoWorkerResult:
    """
    Validate that ffprobe can parse the file and find a video stream.

    Duration is checked here because long videos can become very expensive for
    downstream extraction, transcription, or frame analysis.
    """
    try:
        probe = ffmpeg.probe(str(path))
    except ffmpeg.Error as exc:
        raise SanitizationError(
            f"Video probe failed: {_ffmpeg_error_message(exc)}",
            modality="video",
            worker="ffprobe",
        ) from exc

    video_streams = [
        stream
        for stream in probe.get("streams", [])
        if stream.get("codec_type") == "video"
    ]
    if not video_streams:
        raise SanitizationError(
            "No video stream found in payload",
            modality="video",
            worker="ffprobe",
        )

    format_info = probe.get("format", {})
    format_name = format_info.get("format_name")
    duration_s = _duration_from_probe(format_info, video_streams)
    first_stream = video_streams[0]
    width = int(first_stream.get("width") or 0)
    height = int(first_stream.get("height") or 0)
    resolution = (width, height) if width and height else None

    if duration_s is not None and duration_s > constants.MAX_VIDEO_DURATION_S:
        return VideoWorkerResult(
            name="ffprobe",
            threat_level=ThreatLevel.HIGH,
            reason=f"Video exceeds max duration: {duration_s:.2f}s",
            duration_s=duration_s,
            format=format_name,
            resolution=resolution,
        )

    return VideoWorkerResult(
        name="ffprobe",
        duration_s=duration_s,
        format=format_name,
        resolution=resolution,
    )


def _metadata_worker(path: Path) -> VideoWorkerResult:
    """
    Inspect container-level metadata with ffprobe.

    Metadata is LOW severity because tags are common, but the sanitizer remuxes
    the video without forwarding those tags.
    """
    try:
        probe = ffmpeg.probe(str(path))
    except ffmpeg.Error as exc:
        raise SanitizationError(
            f"Video metadata probe failed: {_ffmpeg_error_message(exc)}",
            modality="video",
            worker="ffprobe",
        ) from exc

    tags = probe.get("format", {}).get("tags", {}) or {}
    metadata_keys = sorted(str(key) for key in tags.keys())
    if not metadata_keys:
        return VideoWorkerResult(name="ffprobe-metadata")

    return VideoWorkerResult(
        name="ffprobe-metadata",
        threat_level=ThreatLevel.LOW,
        reason=f"Video metadata stripped: {', '.join(metadata_keys)}",
        metadata_keys=metadata_keys,
    )


def _sanitize_worker(path: Path) -> VideoWorkerResult:
    """
    Strip metadata with stream copy, preserving original video/audio streams.

    This is quality-first and fast: no codec changes and no lossy generation
    loss. If ffmpeg cannot remux the codec/container losslessly, the validated
    original bytes are preserved instead.
    """
    output_format, output_suffix, extra_flags = _video_output_container(path)
    output_path = path.with_suffix(f".sanitized{output_suffix}")
    try:
        (
            ffmpeg
            .input(str(path))
            .output(
                str(output_path),
                format=output_format,
                vcodec="copy",
                acodec="copy",
                **{"map_metadata": "-1", **extra_flags},
            )
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True, quiet=True)
        )
    except ffmpeg.Error as exc:
        return VideoWorkerResult(
            name="ffmpeg-sanitize",
            threat_level=ThreatLevel.LOW,
            reason=f"Video validated; lossless metadata strip unavailable: {_ffmpeg_error_message(exc)}",
            sanitized_video=path.read_bytes(),
            format="original",
        )

    return VideoWorkerResult(
        name="ffmpeg-sanitize",
        threat_level=ThreatLevel.LOW,
        reason="Video metadata stripped with lossless stream copy",
        sanitized_video=output_path.read_bytes(),
        format=output_format,
    )


def _video_output_container(path: Path) -> tuple[str, str, dict[str, str]]:
    """Choose a remux container that preserves quality with codec copy."""
    try:
        probe = ffmpeg.probe(str(path))
    except ffmpeg.Error:
        return "matroska", ".mkv", {}

    format_name = probe.get("format", {}).get("format_name", "") or ""
    names = set(format_name.split(","))

    if names & {"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}:
        return "mp4", ".mp4", {"movflags": "+faststart"}
    if names & {"matroska"}:
        return "matroska", ".mkv", {}
    if names & {"webm"}:
        return "webm", ".webm", {}

    return "matroska", ".mkv", {}


def _highest_threat(results: list[VideoWorkerResult]) -> ThreatLevel:
    """Return the most severe threat level reported by video sub-workers."""
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


def _run_worker(worker: VideoWorker, path: Path) -> VideoWorkerResult:
    """Run one video sub-worker and wrap unexpected errors with context."""
    try:
        return worker(path)
    except SanitizationError:
        raise
    except Exception as exc:
        worker_name = worker.__name__.removeprefix("_").removesuffix("_worker")
        raise SanitizationError(
            f"Video sanitizer worker failed: {exc}",
            modality="video",
            worker=worker_name,
        ) from exc


def _scan_sync(video: Any) -> VideoScanResult:
    """
    Run all video sanitizer checks and aggregate their results synchronously.

    A temporary input file is used because ffmpeg/ffprobe operate most reliably
    on file paths. scan() offloads this blocking work to a thread.
    """
    payload = _payload_to_bytes(video)

    with tempfile.TemporaryDirectory() as tmp_dir:
        input_path = Path(tmp_dir) / "input.video"
        input_path.write_bytes(payload)

        results = [
            _run_worker(_probe_worker, input_path),
            _run_worker(_metadata_worker, input_path),
            _run_worker(_sanitize_worker, input_path),
        ]

    threat_level = _highest_threat(results)
    reasons = [result.reason for result in results if result.reason]
    sanitized_video = next(
        (result.sanitized_video for result in results if result.sanitized_video is not None),
        None,
    )
    duration_s = next(
        (result.duration_s for result in results if result.duration_s is not None),
        None,
    )
    format_name = next(
        (result.format for result in results if result.format is not None),
        None,
    )
    metadata_keys = next(
        (result.metadata_keys for result in results if result.metadata_keys is not None),
        None,
    )
    resolution = next(
        (result.resolution for result in results if result.resolution is not None),
        None,
    )

    return VideoScanResult(
        threat_level=threat_level,
        reason="; ".join(reasons) if reasons else None,
        passed=not threat_level.should_block,
        sanitized_video=sanitized_video,
        duration_s=duration_s,
        format=format_name,
        metadata_keys=metadata_keys,
        resolution=resolution,
    )


async def scan(video: Any) -> VideoScanResult:
    """
    Async entry point used by the sanitizer runner.

    Video probing and remuxing are blocking operations, so the synchronous
    scan is offloaded to a thread while other modality workers can run.
    """
    return await asyncio.to_thread(_scan_sync, video)
