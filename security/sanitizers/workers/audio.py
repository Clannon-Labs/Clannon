"""
Audio sanitizer worker.

This module runs after universal pre-sanitization has already scanned the raw
payload with ClamAV/YARA. Audio sanitization focuses on parser safety, resource
limits, and metadata stripping before later stages transcribe or otherwise
process the audio.

The worker uses:

* ffmpeg/ffprobe, through ffmpeg-python, to validate and remux audio.
* mutagen to inspect metadata tags.

scan() is only the async entry point. _scan_sync() contains the real blocking
work and is offloaded to a thread by scan().
"""

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Any, Callable

import ffmpeg
from mutagen import File as MutagenFile

from foundation import SanitizationError, ThreatLevel, constants


@dataclass
class AudioWorkerResult:
    """Internal result returned by one audio sub-worker."""
    name: str
    threat_level: ThreatLevel = ThreatLevel.NONE
    reason: str | None = None
    sanitized_audio: bytes | None = None
    duration_s: float | None = None
    format: str | None = None
    metadata_keys: list[str] | None = None

    @property
    def passed(self) -> bool:
        return not self.threat_level.should_block


@dataclass
class AudioScanResult:
    """Public result returned to security/sanitizers/runner.py."""
    threat_level: ThreatLevel
    reason: str | None = None
    passed: bool = True
    sanitized_audio: bytes | None = None
    duration_s: float | None = None
    format: str | None = None
    metadata_keys: list[str] | None = None


AudioWorker = Callable[[Path], AudioWorkerResult]


def _payload_to_bytes(audio: Any) -> bytes:
    """Normalize supported audio inputs into bytes."""
    if isinstance(audio, bytes):
        return audio
    if isinstance(audio, bytearray):
        return bytes(audio)
    if isinstance(audio, memoryview):
        return audio.tobytes()
    if isinstance(audio, os.PathLike):
        return Path(audio).read_bytes()

    raise SanitizationError(
        "Audio sanitizer expected bytes or an audio file path",
        modality="audio",
        worker="audio",
    )


def _ffmpeg_error_message(exc: ffmpeg.Error) -> str:
    """Return a readable ffmpeg/ffprobe error message."""
    stderr = getattr(exc, "stderr", None)
    if isinstance(stderr, bytes):
        return stderr.decode("utf-8", errors="replace").strip()
    if stderr:
        return str(stderr)
    return str(exc)


def _probe_worker(path: Path) -> AudioWorkerResult:
    """
    Validate that ffprobe can parse the file and find an audio stream.

    Duration is checked here because extremely long audio can become expensive
    for transcription or downstream processing.
    """
    try:
        probe = ffmpeg.probe(str(path))
    except ffmpeg.Error as exc:
        raise SanitizationError(
            f"Audio probe failed: {_ffmpeg_error_message(exc)}",
            modality="audio",
            worker="ffprobe",
        ) from exc

    audio_streams = [
        stream
        for stream in probe.get("streams", [])
        if stream.get("codec_type") == "audio"
    ]
    if not audio_streams:
        raise SanitizationError(
            "No audio stream found in payload",
            modality="audio",
            worker="ffprobe",
        )

    format_info = probe.get("format", {})
    format_name = format_info.get("format_name")
    duration_s = _duration_from_probe(format_info, audio_streams)

    if duration_s is not None and duration_s > constants.MAX_AUDIO_DURATION_S:
        return AudioWorkerResult(
            name="ffprobe",
            threat_level=ThreatLevel.HIGH,
            reason=f"Audio exceeds max duration: {duration_s:.2f}s",
            duration_s=duration_s,
            format=format_name,
        )

    return AudioWorkerResult(
        name="ffprobe",
        duration_s=duration_s,
        format=format_name,
    )


def _duration_from_probe(
    format_info: dict[str, Any],
    audio_streams: list[dict[str, Any]],
) -> float | None:
    """Extract duration from ffprobe format data or the first audio stream."""
    candidates = [format_info.get("duration")]
    candidates.extend(stream.get("duration") for stream in audio_streams)

    for candidate in candidates:
        if candidate is None:
            continue
        try:
            return float(candidate)
        except (TypeError, ValueError):
            continue
    return None


def _metadata_worker(path: Path) -> AudioWorkerResult:
    """
    Inspect audio metadata with mutagen.

    Metadata is LOW severity because tags are common, but we still report them
    and the sanitizer remuxes the audio without carrying those tags forward.
    """
    try:
        parsed = MutagenFile(str(path), easy=False)
    except Exception as exc:
        raise SanitizationError(
            f"Audio metadata inspection failed: {exc}",
            modality="audio",
            worker="mutagen",
        ) from exc

    if not parsed or not parsed.tags:
        return AudioWorkerResult(name="mutagen")

    metadata_keys = sorted(str(key) for key in parsed.tags.keys())
    return AudioWorkerResult(
        name="mutagen",
        threat_level=ThreatLevel.LOW,
        reason=f"Audio metadata stripped: {', '.join(metadata_keys)}",
        metadata_keys=metadata_keys,
    )


def _sanitize_worker(path: Path) -> AudioWorkerResult:
    """
    Strip metadata with stream copy, preserving the original encoded audio.

    This is quality-first and fast: no sample-rate changes, no codec changes,
    and no lossy generation loss. If ffmpeg cannot remux the codec/container
    losslessly, the validated original bytes are preserved instead.
    """
    output_format, output_suffix = _audio_output_container(path)
    output_path = path.with_suffix(f".sanitized{output_suffix}")
    try:
        (
            ffmpeg
            .input(str(path))
            .output(
                str(output_path),
                format=output_format,
                acodec="copy",
                **{"map_metadata": "-1", "vn": None},
            )
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True, quiet=True)
        )
    except ffmpeg.Error as exc:
        return AudioWorkerResult(
            name="ffmpeg-sanitize",
            threat_level=ThreatLevel.LOW,
            reason=f"Audio validated; lossless metadata strip unavailable: {_ffmpeg_error_message(exc)}",
            sanitized_audio=path.read_bytes(),
            format="original",
        )

    return AudioWorkerResult(
        name="ffmpeg-sanitize",
        threat_level=ThreatLevel.LOW,
        reason="Audio metadata stripped with lossless stream copy",
        sanitized_audio=output_path.read_bytes(),
        format=output_format,
    )


def _audio_output_container(path: Path) -> tuple[str, str]:
    """Choose a remux container that preserves audio quality with codec copy."""
    try:
        probe = ffmpeg.probe(str(path))
    except ffmpeg.Error:
        return "matroska", ".mka"

    format_name = probe.get("format", {}).get("format_name", "") or ""
    names = set(format_name.split(","))

    if names & {"mp3"}:
        return "mp3", ".mp3"
    if names & {"wav"}:
        return "wav", ".wav"
    if names & {"flac"}:
        return "flac", ".flac"
    if names & {"ogg"}:
        return "ogg", ".ogg"
    if names & {"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}:
        return "ipod", ".m4a"
    if names & {"matroska", "webm"}:
        return "matroska", ".mka"

    return "matroska", ".mka"


def _highest_threat(results: list[AudioWorkerResult]) -> ThreatLevel:
    """Return the most severe threat level reported by audio sub-workers."""
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


def _run_worker(worker: AudioWorker, path: Path) -> AudioWorkerResult:
    """Run one audio sub-worker and wrap unexpected errors with context."""
    try:
        return worker(path)
    except SanitizationError:
        raise
    except Exception as exc:
        worker_name = worker.__name__.removeprefix("_").removesuffix("_worker")
        raise SanitizationError(
            f"Audio sanitizer worker failed: {exc}",
            modality="audio",
            worker=worker_name,
        ) from exc


def _scan_sync(audio: Any) -> AudioScanResult:
    """
    Run all audio sanitizer checks and aggregate their results synchronously.

    A temporary input file is used because ffmpeg and mutagen both operate most
    reliably on file paths. scan() offloads this blocking work to a thread.
    """
    payload = _payload_to_bytes(audio)

    with tempfile.TemporaryDirectory() as tmp_dir:
        input_path = Path(tmp_dir) / "input.audio"
        input_path.write_bytes(payload)

        results = [
            _run_worker(_probe_worker, input_path),
            _run_worker(_metadata_worker, input_path),
            _run_worker(_sanitize_worker, input_path),
        ]

    threat_level = _highest_threat(results)
    reasons = [result.reason for result in results if result.reason]
    sanitized_audio = next(
        (result.sanitized_audio for result in results if result.sanitized_audio is not None),
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

    return AudioScanResult(
        threat_level=threat_level,
        reason="; ".join(reasons) if reasons else None,
        passed=not threat_level.should_block,
        sanitized_audio=sanitized_audio,
        duration_s=duration_s,
        format=format_name,
        metadata_keys=metadata_keys,
    )


async def scan(audio: Any) -> AudioScanResult:
    """
    Async entry point used by the sanitizer runner.

    Audio probing and remuxing are blocking operations, so the synchronous
    scan is offloaded to a thread while other modality workers can run.
    """
    return await asyncio.to_thread(_scan_sync, audio)
