"""
Hermetic contract harness for per-modality sanitizer WORKER scan() internals.

Complements (does NOT duplicate):
  tests/sanitizer_runner.py   -- runner DISPATCH ladder only (monkeypatches text.scan)
  tests/text_sanitization.py  -- text worker internal contracts only
  tests/pre_sanitization.py   -- ClamAV/YARA pre-gate only
  tests/uploads.py            -- malware pre-gate for uploaded files (NOT modality workers)

Dependencies:
  Image: real Pillow (hermetic in-memory payloads); subprocess.run MONKEYPATCHED for
         exiftool so no exiftool binary is required.
  PDF:   real pikepdf + PyMuPDF/fitz (hermetic in-memory payloads); fitz.open
         MONKEYPATCHED for the page-count test so no 500-page PDF is needed.
  Audio: ffmpeg.probe MONKEYPATCHED (probe-path tests); sub-workers MONKEYPATCHED for
         the happy-path aggregation test. ffmpeg BINARY IS NOT REQUIRED.
  Video: same strategy as audio. ffmpeg BINARY IS NOT REQUIRED.

NEEDS-REVIEWER NOTE:
  Audio/video _sanitize_worker (the actual ffmpeg remux step and output-path read) cannot
  be exercised hermetically without the ffmpeg binary. The happy-path tests here pin the
  _scan_sync aggregation via monkeypatched sub-workers, which proves the structured result
  contract (threat_level + reason + passed + payload field) holds. A separate integration
  test against a real binary is needed to pin the lossless-remux path itself.

Serves: Critical Benchmark 5 (per-modality sanitizer workers detect + classify + strip
media hazards under adversarial input) and Critical Benchmark 3 (multimodal
ingestion-security correctness).
"""

import asyncio
import io
import subprocess as _subprocess
from pathlib import Path

import fitz
import pikepdf
import pytest
from PIL import Image as PIL_Image

import settings
from foundation import SanitizationError, ThreatLevel
from security.sanitizers.workers import audio as audio_worker
from security.sanitizers.workers import image as image_worker
from security.sanitizers.workers import pdf as pdf_worker
from security.sanitizers.workers import video as video_worker


# ── in-memory fixture builders ────────────────────────────────────────────────

def _png(width: int = 1, height: int = 1) -> bytes:
    img = PIL_Image.new("L", (width, height), color=0)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_with_exif() -> bytes:
    img = PIL_Image.new("RGB", (10, 10), color=(200, 100, 50))
    exif = img.getexif()
    exif[0x010E] = "TestDescription"  # ImageDescription tag
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


def _minimal_pdf() -> bytes:
    pdf = pikepdf.Pdf.new()
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def _pdf_with_keys(*keys: str) -> bytes:
    pdf = pikepdf.Pdf.new()
    for key in keys:
        pdf.Root[key] = pikepdf.Dictionary()
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


# ── outcome tracking for the summary table ────────────────────────────────────

_OUTCOMES: list[tuple[str, str, str]] = []  # (worker, branch, outcome)


def _record(worker: str, branch: str, outcome: str) -> None:
    _OUTCOMES.append((worker, branch, outcome))


_EXPECTED_CONTRACTS = [
    ("image", "valid-image-passes"),
    ("image", "metadata-stripped-losslessly"),
    ("image", "exiftool-timeout-preserves-original"),
    ("image", "exiftool-nonzero-preserves-original"),
    ("image", "oversized-dimension-rejected"),
    ("image", "non-image-bytes-rejected"),
    ("image", "decompression-bomb-rejected"),
    ("pdf", "non-pdf-header-rejected"),
    ("pdf", "page-count-exceeded-rejected"),
    ("pdf", "dangerous-entries-stripped"),
    ("pdf", "clean-pdf-passes"),
    ("audio", "probe-duration-exceeded-rejected"),
    ("audio", "probe-no-stream-rejected"),
    ("audio", "valid-probe-aggregation-passes"),
    ("video", "probe-duration-exceeded-rejected"),
    ("video", "probe-no-stream-rejected"),
    ("video", "valid-probe-aggregation-passes"),
]


# ═══════════════════════════════════════════════════════════════════════════════
# IMAGE WORKER
# Pillow is a real dep. exiftool subprocess.run is MONKEYPATCHED throughout.
# ═══════════════════════════════════════════════════════════════════════════════

def test_image_valid_image_passes_with_format_and_size():
    """A valid in-memory PNG with no metadata passes; format and size are populated."""
    payload = _png(1, 1)
    result = image_worker._scan_sync(payload)

    assert result.passed is True
    assert result.threat_level == ThreatLevel.NONE
    assert result.format == "PNG"
    assert result.size == (1, 1)
    assert result.sanitized_image is not None

    _record("image", "valid-image-passes", "VALIDATED")


def test_image_metadata_stripped_losslessly(monkeypatch):
    """
    A JPEG carrying EXIF metadata is stripped losslessly.

    sanitized_image != input confirms stripping occurred; threat_level=LOW
    (not blocking) and reason is set per image.py:148-150.
    """
    payload = _jpeg_with_exif()
    assert image_worker._has_metadata(payload), "fixture must have metadata"

    def _fake_exiftool(cmd, **kwargs):
        p = Path(cmd[-1])
        data = p.read_bytes()
        # Write fewer bytes to simulate exiftool stripping EXIF in-place.
        p.write_bytes(data[:max(1, len(data) - 50)])
        return _subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr(image_worker.subprocess, "run", _fake_exiftool)

    result = image_worker._scan_sync(payload)

    assert result.threat_level == ThreatLevel.LOW
    assert result.reason is not None
    assert "stripped" in result.reason.lower()
    assert result.sanitized_image != payload
    assert result.passed is True  # LOW does not block (should_block is HIGH+CRITICAL only)
    assert result.format == "JPEG"
    assert result.size == (10, 10)

    _record("image", "metadata-stripped-losslessly", "STRIPPED")


def test_image_exiftool_timeout_preserves_original_bytes(monkeypatch):
    """
    When exiftool hangs past the deadline the ORIGINAL validated bytes are
    returned unchanged, never a degraded payload (image.py:130-133).
    """
    payload = _jpeg_with_exif()

    def _fake_timeout(cmd, **kwargs):
        raise _subprocess.TimeoutExpired(cmd=cmd, timeout=10)

    monkeypatch.setattr(image_worker.subprocess, "run", _fake_timeout)

    result = image_worker._scan_sync(payload)

    # Original bytes are preserved; the image is not degraded.
    assert result.sanitized_image == payload
    assert result.passed is True
    # threat_level stays NONE because sanitized == original (no strip occurred)
    assert result.threat_level == ThreatLevel.NONE

    _record("image", "exiftool-timeout-preserves-original", "PRESERVED-ON-TOOL-FAIL")


def test_image_exiftool_nonzero_return_preserves_original_bytes(monkeypatch):
    """
    When exiftool exits non-zero the ORIGINAL validated bytes are returned
    unchanged (image.py:134-135). Never degrade a valid image on tool failure.
    """
    payload = _jpeg_with_exif()

    def _fake_fail(cmd, **kwargs):
        return _subprocess.CompletedProcess(args=cmd, returncode=1)

    monkeypatch.setattr(image_worker.subprocess, "run", _fake_fail)

    result = image_worker._scan_sync(payload)

    assert result.sanitized_image == payload
    assert result.passed is True
    assert result.threat_level == ThreatLevel.NONE

    _record("image", "exiftool-nonzero-preserves-original", "PRESERVED-ON-TOOL-FAIL")


def test_image_oversized_dimension_raises_sanitization_error():
    """
    An image whose largest dimension exceeds MAX_IMAGE_DIMENSION_PX raises
    SanitizationError before any metadata or pixel work (image.py:79-84).
    """
    oversized = _png(settings.SECURITY.max_image_dimension_px + 1, 1)

    with pytest.raises(SanitizationError) as exc_info:
        image_worker._scan_sync(oversized)

    assert "dimension exceeds limit" in str(exc_info.value).lower()
    assert exc_info.value.modality == "image"

    _record("image", "oversized-dimension-rejected", "REJECTED")


def test_image_non_image_bytes_raise_sanitization_error():
    """
    Bytes that are not a recognisable image format raise SanitizationError
    at the Pillow parsing step (image.py:71-76).
    """
    with pytest.raises(SanitizationError) as exc_info:
        image_worker._scan_sync(b"THIS IS NOT AN IMAGE PAYLOAD")

    assert exc_info.value.modality == "image"

    _record("image", "non-image-bytes-rejected", "REJECTED")


def test_image_decompression_bomb_raises_sanitization_error(monkeypatch):
    """
    When Pillow raises DecompressionBombError the worker converts it to
    SanitizationError so the runner never sees a raw Pillow exception
    (image.py:65-70).
    """
    bomb_exc = PIL_Image.DecompressionBombError("simulated oversized image")

    def _mock_open(_fp):
        raise bomb_exc

    monkeypatch.setattr(image_worker.Image, "open", _mock_open)

    with pytest.raises(SanitizationError) as exc_info:
        image_worker._scan_sync(b"fake_image_bytes")

    assert "decompression bomb" in str(exc_info.value).lower()
    assert exc_info.value.modality == "image"

    _record("image", "decompression-bomb-rejected", "REJECTED")


# ═══════════════════════════════════════════════════════════════════════════════
# PDF WORKER
# pikepdf and PyMuPDF/fitz are real deps. fitz.open MONKEYPATCHED for page test.
# ═══════════════════════════════════════════════════════════════════════════════

def test_pdf_non_pdf_header_rejected():
    """
    A payload without a %%PDF- header is rejected at the structure check before
    pikepdf tries to parse the object graph (pdf.py:88-100).
    """
    with pytest.raises(SanitizationError) as exc_info:
        pdf_worker._structure_worker(b"NOT A PDF FILE AT ALL")

    assert "missing %PDF header" in str(exc_info.value)
    assert exc_info.value.modality == "pdf"

    _record("pdf", "non-pdf-header-rejected", "REJECTED")


def test_pdf_page_count_exceeded_rejected(monkeypatch):
    """
    A PDF whose page count exceeds MAX_PDF_PAGES is rejected (pdf.py:147-153).
    fitz.open is monkeypatched so no 500-page document is needed.
    """
    class _FakeDoc:
        page_count = settings.SECURITY.max_pdf_pages + 1

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    monkeypatch.setattr(fitz, "open", lambda *args, **kwargs: _FakeDoc())

    result = pdf_worker._page_count_worker(b"%PDF-1.4 fake content")

    assert result.threat_level == ThreatLevel.HIGH
    assert result.passed is False
    assert result.page_count is not None
    assert result.page_count > settings.SECURITY.max_pdf_pages
    assert "exceeds max page count" in (result.reason or "")

    _record("pdf", "page-count-exceeded-rejected", "REJECTED")


def test_pdf_dangerous_entries_stripped():
    """
    A PDF carrying /JavaScript and /OpenAction entries has both stripped by
    _sanitize_worker (pdf.py:158-231); threat_level=MEDIUM, passed=True (not blocking).
    """
    dangerous = _pdf_with_keys("/JavaScript", "/OpenAction")

    result = pdf_worker._sanitize_worker(dangerous)

    assert result.threat_level == ThreatLevel.MEDIUM
    assert result.passed  # MEDIUM is should_warn, not should_block
    assert result.reason is not None
    assert "/JavaScript" in result.reason or "/OpenAction" in result.reason
    assert result.sanitized_pdf is not None
    # Dangerous keys must not appear in the re-saved output
    assert b"/JavaScript" not in result.sanitized_pdf
    assert b"/OpenAction" not in result.sanitized_pdf

    _record("pdf", "dangerous-entries-stripped", "STRIPPED")


def test_pdf_clean_pdf_passes():
    """
    A clean minimal PDF passes full scan with passed=True.

    pikepdf re-saves and normalises the structure, so the sanitized bytes differ
    from the raw input (threat_level=LOW) but the document is never blocked.
    """
    result = pdf_worker._scan_sync(_minimal_pdf())

    assert result.passed is True
    assert not result.threat_level.should_block
    assert result.sanitized_pdf is not None
    assert result.page_count is not None

    _record("pdf", "clean-pdf-passes", "VALIDATED")


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIO WORKER
# ffmpeg.probe MONKEYPATCHED on the module; sub-workers MONKEYPATCHED for
# the happy-path aggregation test. NO ffmpeg binary required.
# ═══════════════════════════════════════════════════════════════════════════════

def test_audio_probe_duration_exceeded_rejected(monkeypatch):
    """
    _probe_worker returns threat_level=HIGH when the probe reports a duration
    exceeding MAX_AUDIO_DURATION_S (audio.py:138-145).
    """
    too_long = float(settings.SECURITY.max_audio_duration_s) + 1.0

    monkeypatch.setattr(
        audio_worker.ffmpeg,
        "probe",
        lambda path: {
            "streams": [{"codec_type": "audio", "duration": str(too_long)}],
            "format": {"format_name": "mp3", "duration": str(too_long)},
        },
    )

    result = audio_worker._probe_worker(Path("/dev/null"))

    assert result.threat_level == ThreatLevel.HIGH
    assert result.passed is False
    assert result.duration_s is not None
    assert result.duration_s > settings.SECURITY.max_audio_duration_s
    assert "exceeds max duration" in (result.reason or "")

    _record("audio", "probe-duration-exceeded-rejected", "REJECTED")


def test_audio_probe_no_audio_stream_rejected(monkeypatch):
    """
    _probe_worker raises SanitizationError when ffprobe finds no audio stream
    in the payload (audio.py:127-132).
    """
    monkeypatch.setattr(
        audio_worker.ffmpeg,
        "probe",
        lambda path: {"streams": [], "format": {"format_name": "mp3"}},
    )

    with pytest.raises(SanitizationError) as exc_info:
        audio_worker._probe_worker(Path("/dev/null"))

    assert "no audio stream" in str(exc_info.value).lower()
    assert exc_info.value.modality == "audio"

    _record("audio", "probe-no-stream-rejected", "REJECTED")


def test_audio_valid_probe_aggregation_passes(monkeypatch):
    """
    _scan_sync aggregates sub-worker results correctly: highest threat wins,
    reasons are joined, and the sanitized payload field is populated.

    Sub-workers are monkeypatched; this isolates _scan_sync aggregation from
    the ffmpeg binary. The documented ThreatLevel for a clean remux is LOW.
    """
    def _fake_probe(path):
        return audio_worker.AudioWorkerResult(
            name="ffprobe",
            duration_s=30.0,
            format="mp3",
        )

    def _fake_metadata(path):
        return audio_worker.AudioWorkerResult(name="mutagen")

    def _fake_sanitize(path):
        return audio_worker.AudioWorkerResult(
            name="ffmpeg-sanitize",
            threat_level=ThreatLevel.LOW,
            reason="Audio metadata stripped with lossless stream copy",
            sanitized_audio=b"remuxed_audio_bytes",
            format="mp3",
        )

    monkeypatch.setattr(audio_worker, "_probe_worker", _fake_probe)
    monkeypatch.setattr(audio_worker, "_metadata_worker", _fake_metadata)
    monkeypatch.setattr(audio_worker, "_sanitize_worker", _fake_sanitize)

    result = asyncio.run(audio_worker.scan(b"any_bytes"))

    assert result.passed is True
    assert result.threat_level == ThreatLevel.LOW
    assert result.sanitized_audio == b"remuxed_audio_bytes"
    assert result.duration_s == 30.0
    assert result.format == "mp3"
    assert result.reason is not None

    _record("audio", "valid-probe-aggregation-passes", "VALIDATED")


# ═══════════════════════════════════════════════════════════════════════════════
# VIDEO WORKER
# Same monkeypatching strategy as audio. NO ffmpeg binary required.
# ═══════════════════════════════════════════════════════════════════════════════

def test_video_probe_duration_exceeded_rejected(monkeypatch):
    """
    _probe_worker returns threat_level=HIGH when probe reports duration exceeding
    MAX_VIDEO_DURATION_S (video.py:157-165).
    """
    too_long = float(settings.SECURITY.max_video_duration_s) + 1.0

    monkeypatch.setattr(
        video_worker.ffmpeg,
        "probe",
        lambda path: {
            "streams": [
                {
                    "codec_type": "video",
                    "duration": str(too_long),
                    "width": 1280,
                    "height": 720,
                }
            ],
            "format": {"format_name": "mp4", "duration": str(too_long)},
        },
    )

    result = video_worker._probe_worker(Path("/dev/null"))

    assert result.threat_level == ThreatLevel.HIGH
    assert result.passed is False
    assert result.duration_s is not None
    assert result.duration_s > settings.SECURITY.max_video_duration_s
    assert "exceeds max duration" in (result.reason or "")

    _record("video", "probe-duration-exceeded-rejected", "REJECTED")


def test_video_probe_no_video_stream_rejected(monkeypatch):
    """
    _probe_worker raises SanitizationError when ffprobe finds no video stream
    (video.py:143-147).
    """
    monkeypatch.setattr(
        video_worker.ffmpeg,
        "probe",
        lambda path: {
            "streams": [{"codec_type": "audio"}],
            "format": {"format_name": "mp4"},
        },
    )

    with pytest.raises(SanitizationError) as exc_info:
        video_worker._probe_worker(Path("/dev/null"))

    assert "no video stream" in str(exc_info.value).lower()
    assert exc_info.value.modality == "video"

    _record("video", "probe-no-stream-rejected", "REJECTED")


def test_video_valid_probe_aggregation_passes(monkeypatch):
    """
    _scan_sync aggregates video sub-worker results correctly: highest threat wins,
    reasons joined, sanitized_video populated, resolution surfaced.

    Sub-workers are monkeypatched; this isolates _scan_sync from the ffmpeg binary.
    """
    def _fake_probe(path):
        return video_worker.VideoWorkerResult(
            name="ffprobe",
            duration_s=60.0,
            format="mp4",
            resolution=(1280, 720),
        )

    def _fake_metadata(path):
        return video_worker.VideoWorkerResult(name="ffprobe-metadata")

    def _fake_sanitize(path):
        return video_worker.VideoWorkerResult(
            name="ffmpeg-sanitize",
            threat_level=ThreatLevel.LOW,
            reason="Video metadata stripped with lossless stream copy",
            sanitized_video=b"remuxed_video_bytes",
            format="mp4",
        )

    monkeypatch.setattr(video_worker, "_probe_worker", _fake_probe)
    monkeypatch.setattr(video_worker, "_metadata_worker", _fake_metadata)
    monkeypatch.setattr(video_worker, "_sanitize_worker", _fake_sanitize)

    result = asyncio.run(video_worker.scan(b"any_bytes"))

    assert result.passed is True
    assert result.threat_level == ThreatLevel.LOW
    assert result.sanitized_video == b"remuxed_video_bytes"
    assert result.duration_s == 60.0
    assert result.format == "mp4"
    assert result.resolution == (1280, 720)
    assert result.reason is not None

    _record("video", "valid-probe-aggregation-passes", "VALIDATED")


# ═══════════════════════════════════════════════════════════════════════════════
# CONTRACT SUMMARY TABLE
# Runs last; prints per-worker per-branch verdict; fails if any contract is absent.
# ═══════════════════════════════════════════════════════════════════════════════

_OUTCOME_LABELS = {
    "VALIDATED": "VALIDATED",
    "REJECTED": "REJECTED",
    "STRIPPED": "STRIPPED",
    "PRESERVED-ON-TOOL-FAIL": "PRESERVED-ON-TOOL-FAIL",
}


def test_zzz_print_contract_summary():
    """
    Print the per-worker per-branch contract verification table and fail if any
    expected contract was not exercised (implying a test failure above).
    """
    held: dict[tuple[str, str], str] = {
        (w, b): o for w, b, o in _OUTCOMES
    }

    header = f"{'Worker':<8}  {'Branch':<42}  {'Outcome':<24}  Verdict"
    separator = "-" * len(header)

    print(f"\n\n{'=':=<{len(header)}}")
    print("  SANITIZER WORKER CONTRACT TABLE")
    print(f"{'=':=<{len(header)}}")
    print(header)
    print(separator)

    violations: list[tuple[str, str]] = []
    for worker, branch in _EXPECTED_CONTRACTS:
        if (worker, branch) in held:
            outcome = held[(worker, branch)]
            verdict = "worker contract held"
        else:
            outcome = "NOT-RUN"
            verdict = "VIOLATED"
            violations.append((worker, branch))

        print(f"{worker:<8}  {branch:<42}  {outcome:<24}  {verdict}")

    print(separator)
    print(
        f"  {len(_EXPECTED_CONTRACTS) - len(violations)}/{len(_EXPECTED_CONTRACTS)} "
        f"contracts held"
        + (f"  |  {len(violations)} VIOLATED" if violations else "")
    )
    print(f"{'=':=<{len(header)}}\n")

    if violations:
        pytest.fail(
            f"Sanitizer worker contracts VIOLATED or not exercised: {violations}"
        )
