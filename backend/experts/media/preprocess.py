"""Local media preprocessing — the approach the big labs use under the hood.

Instead of throwing raw bytes at a multimodal model and hoping (slow, rate-limit-prone,
inline-size-capped, and impossible on a model that can't read that modality), we turn
each attached file into **model-ready inputs**: extracted text plus images. The model
then reasons over the text and SEES the visuals. This is fast, mostly local (no per-file
API call), and provider-independent — a plain text/vision model can understand any media
once it's been preprocessed, so a run survives the multimodal provider being down.

    preprocess(name, mime, data) -> (texts, media)
      texts : list[str]            extracted/transcribed text to inline into the prompt
      media : list[(bytes, mime)]  images (or, when nothing local applies, the raw bytes)
                                   to hand the multimodal model as BinaryContent

Per modality:
- PDF   -> text (PyMuPDF) + rendered page images for pages with visual content / scans
- image -> the image itself at full resolution (so the model sees small details)
- audio -> transcript (faster-whisper)            [added in the audio/video pass]
- video -> transcript + sampled key frames        [added in the audio/video pass]
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
import threading

import settings
from foundation import get_root

# PDF/transcript/video bounds live in config/backend/experts.yaml (settings.EXPERTS) —
# see there for values + rationale. Only the env-driven deployment paths below stay
# module constants (not product dials).

# Audio/video: transcribe with faster-whisper (CTranslate2 — fast, low-memory on CPU) and
# sample video frames with ffmpeg, so any model can understand them and a run survives the
# multimodal provider being down. The model downloads once into a persistent cache.
#
# HONEST CAPABILITY NOTE (Law 5 — no hidden capability): on a cold cache, _get_whisper()
# below makes ONE outbound fetch to Hugging Face Hub for the model weights named by
# _WHISPER_MODEL. This is the media expert's only network touch despite its declared
# `permission = PermissionLevel.READ` (see experts/media/expert.py) — safe to leave
# undeclared as a grant because the target is FIXED (an ops env var, one of a small
# named set, never request/user-derived) and the fetch is ONE-TIME per (model,
# cache-dir): the process-global `_whisper` cache below plus the on-disk download_root
# mean a warm environment never repeats it. Not an SSRF surface (nothing here resolves
# a request-supplied URL) and not exfiltration (outbound-only, fetches public weights,
# sends no user data). Flagged here so a reader auditing READ-vs-actual-behavior finds
# this without reading faster_whisper's internals.
_WHISPER_MODEL = os.getenv("VRAKSHA_WHISPER_MODEL", "base")    # tiny/base/small/medium/large-v3
_WHISPER_CACHE = os.getenv("VRAKSHA_WHISPER_CACHE") or str(get_root() / "assets" / "whisper_cache")
_MEDIA_TMP = os.getenv("VRAKSHA_MEDIA_TMP") or None   # temp dir for av decode (None = system tmp)

_whisper = None
_whisper_lock = threading.Lock()


def _pdf_sync(data: bytes) -> tuple[str, list[bytes]]:
    """Extract text and render the visually-meaningful pages of a PDF to PNGs. A text PDF
    yields text (+ any pages that carry raster images, e.g. charts); a scanned PDF yields
    no text, so its pages are rendered for the model to read. Both are bounded."""
    import fitz  # PyMuPDF — the same lib the PDF sanitizer uses

    texts: list[str] = []
    pages_png: list[bytes] = []
    total = 0
    with fitz.open(stream=data, filetype="pdf") as doc:
        for page in doc:
            text = page.get_text().strip()
            if text:
                texts.append(text)
                total += len(text)
            # render a page when it carries raster images (charts/photos) or when the
            # document has no extractable text at all (scanned) — bounded by the cap
            wants_render = bool(page.get_images()) or not text
            if wants_render and len(pages_png) < settings.EXPERTS.max_pdf_render_pages:
                pages_png.append(page.get_pixmap(dpi=settings.EXPERTS.pdf_render_dpi).tobytes("png"))
            if total >= settings.EXPERTS.max_doc_chars:
                break
    return "\n\n".join(texts)[:settings.EXPERTS.max_doc_chars], pages_png


async def _pdf(data: bytes) -> tuple[list[str], list[tuple[bytes, str]]]:
    try:
        text, pages = await asyncio.to_thread(_pdf_sync, data)
    except Exception:  # noqa: BLE001 — PyMuPDF couldn't parse it
        text, pages = "", []
    texts = [text] if len(text) >= settings.EXPERTS.min_pdf_text_chars else []
    media = [(png, "image/png") for png in pages]
    if not texts and not media:
        # we extracted nothing locally (encrypted/odd/empty PDF) — don't drop it; hand the
        # raw bytes to the multimodal model, which may still read it
        return [], [(data, "application/pdf")]
    return texts, media


# ---- audio: local transcription (faster-whisper) ---------------------------


def _get_whisper():
    """Load the faster-whisper model once (thread-safe), cached on disk after first use."""
    global _whisper
    if _whisper is None:
        with _whisper_lock:
            if _whisper is None:
                from faster_whisper import WhisperModel
                _whisper = WhisperModel(
                    _WHISPER_MODEL, device="cpu", compute_type="int8", download_root=_WHISPER_CACHE
                )
    return _whisper


def _transcribe(path: str) -> str:
    segments, _info = _get_whisper().transcribe(path, vad_filter=True)
    return " ".join(s.text.strip() for s in segments).strip()[:settings.EXPERTS.max_transcript_chars]


def _audio_sync(data: bytes, suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix, dir=_MEDIA_TMP)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        return _transcribe(path)
    finally:
        os.unlink(path)


async def _audio(data: bytes, mime: str) -> tuple[list[str], list[tuple[bytes, str]]]:
    try:
        suffix = "." + (mime.split("/", 1)[1] if "/" in mime else "audio")
        text = await asyncio.to_thread(_audio_sync, data, suffix)
    except Exception:  # noqa: BLE001 — transcription unavailable/failed -> let the model try
        text = ""
    if text:
        return [f"[audio transcript] {text}"], []
    return [], [(data, mime)]   # empty/failed -> hand the raw audio to the multimodal model


# ---- video: ffmpeg -> extracted audio (transcribe) + sampled frames --------


def _video_sync(data: bytes, suffix: str) -> tuple[str, list[bytes]]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not available")
    work = tempfile.mkdtemp(dir=_MEDIA_TMP)
    try:
        src = os.path.join(work, "in" + suffix)
        with open(src, "wb") as fh:
            fh.write(data)

        # audio track -> mono 16k wav -> transcript (best-effort: a silent video has none)
        wav = os.path.join(work, "audio.wav")
        subprocess.run([ffmpeg, "-nostdin", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000", wav],
                       capture_output=True, timeout=settings.EXPERTS.ffmpeg_timeout_s)
        transcript = _transcribe(wav) if os.path.exists(wav) and os.path.getsize(wav) > 0 else ""

        # one frame every N seconds, capped, for the model to SEE
        subprocess.run([ffmpeg, "-nostdin", "-y", "-i", src, "-vf",
                        f"fps=1/{settings.EXPERTS.video_frame_every_s}",
                        "-frames:v", str(settings.EXPERTS.max_video_frames), os.path.join(work, "f_%03d.png")],
                       capture_output=True, timeout=settings.EXPERTS.ffmpeg_timeout_s)
        frames: list[bytes] = []
        for i in range(1, settings.EXPERTS.max_video_frames + 1):
            fp = os.path.join(work, f"f_{i:03d}.png")
            if os.path.exists(fp):
                with open(fp, "rb") as fh:
                    frames.append(fh.read())
        return transcript, frames
    finally:
        shutil.rmtree(work, ignore_errors=True)


async def _video(data: bytes, mime: str) -> tuple[list[str], list[tuple[bytes, str]]]:
    try:
        suffix = "." + (mime.split("/", 1)[1] if "/" in mime else "mp4")
        transcript, frames = await asyncio.to_thread(_video_sync, data, suffix)
    except Exception:  # noqa: BLE001 — ffmpeg/whisper unavailable -> let the model try the raw video
        return [], [(data, mime)]
    texts = [f"[video transcript] {transcript}"] if transcript else []
    media = [(png, "image/png") for png in frames]
    if not texts and not media:
        return [], [(data, mime)]   # extracted nothing -> raw fallback
    return texts, media


async def preprocess(name: str, mime: str, data: bytes) -> tuple[list[str], list[tuple[bytes, str]]]:
    """Turn one attached file into (texts, media) for the model. Unknown types fall back to
    handing the raw bytes to the multimodal model."""
    if mime == "application/pdf":
        return await _pdf(data)
    if mime.startswith("audio/"):
        return await _audio(data, mime)
    if mime.startswith("video/"):
        return await _video(data, mime)
    # images ride at full resolution so the model sees fine detail
    return [], [(data, mime)]
