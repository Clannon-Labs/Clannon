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

# PDF: how much text to inline, and how many pages to render (visual content) and at what
# resolution. 150 DPI keeps small details legible without ballooning the request.
_MAX_DOC_CHARS = 50_000
_MIN_PDF_TEXT = 50              # below this the PDF is effectively scanned -> render it
_PDF_RENDER_DPI = 150
_MAX_PDF_RENDER_PAGES = 8       # cap rendered pages so a long PDF can't explode the request


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
            if wants_render and len(pages_png) < _MAX_PDF_RENDER_PAGES:
                pages_png.append(page.get_pixmap(dpi=_PDF_RENDER_DPI).tobytes("png"))
            if total >= _MAX_DOC_CHARS:
                break
    return "\n\n".join(texts)[:_MAX_DOC_CHARS], pages_png


async def _pdf(data: bytes) -> tuple[list[str], list[tuple[bytes, str]]]:
    try:
        text, pages = await asyncio.to_thread(_pdf_sync, data)
    except Exception:  # noqa: BLE001 — PyMuPDF couldn't parse it
        text, pages = "", []
    texts = [text] if len(text) >= _MIN_PDF_TEXT else []
    media = [(png, "image/png") for png in pages]
    if not texts and not media:
        # we extracted nothing locally (encrypted/odd/empty PDF) — don't drop it; hand the
        # raw bytes to the multimodal model, which may still read it
        return [], [(data, "application/pdf")]
    return texts, media


async def preprocess(name: str, mime: str, data: bytes) -> tuple[list[str], list[tuple[bytes, str]]]:
    """Turn one attached file into (texts, media) for the model. Unknown types fall back to
    handing the raw bytes to the multimodal model."""
    if mime == "application/pdf":
        return await _pdf(data)
    # images ride at full resolution so the model sees fine detail; audio/video fall back
    # to the multimodal model here until the audio/video preprocessing lands.
    return [], [(data, mime)]
