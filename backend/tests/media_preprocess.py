"""Local media preprocessing (experts/media/preprocess.py): each file becomes
model-ready (texts + images) with local tools, so the model reasons over text and SEES
the visuals, fast and provider-independently."""

import asyncio
import shutil
import subprocess

import fitz  # PyMuPDF
import pytest

import experts.media.preprocess as pp
from experts.media.preprocess import preprocess


def _run(name, mime, data):
    return asyncio.run(preprocess(name, mime, data))


_HAS_FFMPEG = shutil.which("ffmpeg") is not None


def test_text_pdf_yields_text_no_images():
    doc = fitz.open()
    doc.new_page().insert_text(
        (72, 72),
        "Quarterly report. Revenue grew to 1.2M in Q3 2026, up 40 percent. "
        "This is a genuine text page with enough text to count as a real document.")
    texts, media = _run("report.pdf", "application/pdf", doc.tobytes())
    assert len(texts) == 1 and "Revenue grew" in texts[0]
    assert media == []                          # no raster images -> nothing to render


def test_scanned_pdf_renders_pages_as_images():
    # a page with an embedded raster image and NO text === a scanned page
    doc = fitz.open()
    page = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 80, 80))
    pix.set_rect(pix.irect, (10, 120, 220))     # a solid colored block
    page.insert_image(fitz.Rect(72, 72, 172, 172), pixmap=pix)
    texts, media = _run("scan.pdf", "application/pdf", doc.tobytes())
    assert texts == []                          # nothing to extract from a scan
    assert len(media) == 1 and media[0][1] == "image/png"   # the page was RENDERED for the model
    assert media[0][0][:8] == b"\x89PNG\r\n\x1a\n"          # real PNG bytes


def test_pdf_render_is_bounded():
    doc = fitz.open()
    for _ in range(20):                         # more pages than the render cap
        page = doc.new_page()
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 20, 20))
        pix.set_rect(pix.irect, (0, 0, 0))
        page.insert_image(fitz.Rect(10, 10, 30, 30), pixmap=pix)
    _texts, media = _run("big.pdf", "application/pdf", doc.tobytes())
    from experts.media.preprocess import _MAX_PDF_RENDER_PAGES
    assert 0 < len(media) <= _MAX_PDF_RENDER_PAGES   # capped, never one-per-page unbounded


def test_image_passes_through_at_full_resolution():
    raw = b"\x89PNG\r\n\x1a\nsome image bytes"
    texts, media = _run("photo.png", "image/png", raw)
    assert texts == []
    assert media == [(raw, "image/png")]        # exact bytes, not downscaled


def test_unparseable_pdf_falls_back_to_raw_bytes():
    texts, media = _run("broken.pdf", "application/pdf", b"%PDF-1.7 not really a pdf")
    # we don't drop it — the multimodal model gets the raw bytes to try
    assert texts == [] and media == [(b"%PDF-1.7 not really a pdf", "application/pdf")]


# ---- audio: transcription (whisper mocked so CI never downloads a model) ----


def test_audio_yields_a_transcript(monkeypatch):
    monkeypatch.setattr(pp, "_transcribe", lambda path: "hello from the recording")
    texts, media = _run("note.wav", "audio/wav", b"RIFFfakeaudio")
    assert texts == ["[audio transcript] hello from the recording"]
    assert media == []                              # transcribed locally, no model audio call


def test_audio_empty_transcript_falls_back_to_the_model(monkeypatch):
    monkeypatch.setattr(pp, "_transcribe", lambda path: "")    # silence / not speech
    raw = b"RIFFfakeaudio"
    texts, media = _run("note.wav", "audio/wav", raw)
    assert texts == [] and media == [(raw, "audio/wav")]       # hand the raw audio to the model


# ---- video: ffmpeg frames + extracted-audio transcript ---------------------


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg not installed")
def test_video_extracts_frames_and_transcript(monkeypatch, tmp_path):
    monkeypatch.setattr(pp, "_transcribe", lambda path: "spoken words in the clip")
    clip = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-y", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=6",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=6", "-shortest", "-pix_fmt", "yuv420p", str(clip)],
        capture_output=True, check=True)
    texts, media = _run("clip.mp4", "video/mp4", clip.read_bytes())
    assert texts == ["[video transcript] spoken words in the clip"]      # audio track transcribed
    assert len(media) >= 1 and all(m == "image/png" for _, m in media)   # frames sampled for the model
    assert media[0][0][:8] == b"\x89PNG\r\n\x1a\n"


def test_video_falls_back_to_raw_when_ffmpeg_missing(monkeypatch):
    monkeypatch.setattr(pp.shutil, "which", lambda _name: None)   # pretend ffmpeg is absent
    raw = b"\x00\x00\x00\x18ftypmp42fakevideo"
    texts, media = _run("clip.mp4", "video/mp4", raw)
    assert texts == [] and media == [(raw, "video/mp4")]         # don't drop it, let the model try
