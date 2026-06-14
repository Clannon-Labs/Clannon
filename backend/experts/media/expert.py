"""Media expert (key: media.analyst) — understands attached media AND documents
(images, audio, video, PDFs). It reads the file seeded into its workspace and reasons
over it with a multimodal model (Gemini by default): describes images and reads their
text (OCR), transcribes and summarizes audio, describes/summarizes video, and reads/
summarizes PDF documents (Gemini reads PDFs natively as a document modality). Its
behavior lives in its system prompt + skills beside this file; this module declares
what it is and how its request + the attached file become the agent's multimodal task.

Note: the file rides INLINE in the model request, so a single very large file (tens of
MB) can exceed the provider's inline limit; that file is skipped and reported instead of
failing the run. A File-API upload path for big files is a later enhancement."""

from __future__ import annotations

import mimetypes

from pydantic import BaseModel, Field

from foundation import PermissionLevel

from registry import expert
from registry.capabilities import ExpertOutput
from registry.capabilities.handler import ExpertEnv, think


class MediaIn(BaseModel):
    """What the orchestrator emits to call this expert (structured, not free text)."""
    prompt: str = Field(
        description="What to do with the attached media or document: describe an image and "
        "read its text (OCR), transcribe or summarize audio, describe or summarize video, "
        "read or summarize a PDF document, or answer a question about its content."
    )


@expert
class MediaExpert:
    name = "analyst"
    domain = "media"
    description = (
        "Understand attached media AND documents (images, audio, video, PDFs) with a "
        "multimodal model: describe images and read their text (OCR), transcribe and "
        "summarize audio, describe and summarize video, read and summarize PDF documents, "
        "and answer questions about the content. The expert for any uploaded PDF, image, "
        "audio, or video."
    )
    input_schema = MediaIn
    output_schema = ExpertOutput
    skills = ("skills",)                # baseline skills/ beside this file
    tools = ("fs.read",)               # grants a per-run workspace so attached media/docs are seeded + readable
    model_role = "media_expert"        # multimodal understanding, Gemini by default
    permission = PermissionLevel.READ
    tags = ("media", "image", "audio", "video", "pdf", "document", "vision", "transcription")

    async def run(self, args: MediaIn, env: ExpertEnv) -> ExpertOutput:
        media, oversized = await _media(env)
        return await think(env, _task(args, oversized), media=media)


# media rides INLINE in the request; a single file past the provider's inline limit
# would 400 the call, so we skip it (and report it) instead of failing the run. A
# File-API upload path for big files is a later enhancement.
_INLINE_LIMIT_BYTES = 15 * 1024 * 1024


def _task(args: MediaIn, oversized: list[tuple[str, int]]) -> str:
    """This expert's per-call task: the request, plus a clear, actionable note about any
    media that was too large to include inline (so the answer stays legible to the user)."""
    task = args.prompt
    if oversized:
        listing = ", ".join(f"{name} (~{size // (1024 * 1024)} MB)" for name, size in oversized)
        limit_mb = _INLINE_LIMIT_BYTES // (1024 * 1024)
        task += (
            f"\n\nNOTE: these attached files were too large to analyze inline and were NOT "
            f"included: {listing}. The inline limit is about {limit_mb} MB. Say this plainly in "
            f"your answer and suggest the user compress or trim them, then analyze whatever "
            f"media WAS included."
        )
    return task


# Map the non-canonical mime forms libmagic/mimetypes emit to the canonical media
# types a multimodal model expects (e.g. audio/x-wav -> audio/wav). Unmapped forms
# pass through unchanged.
_MIME_ALIASES = {
    "audio/x-wav": "audio/wav",
    "audio/wave": "audio/wav",
    "audio/vnd.wave": "audio/wav",
    "audio/mpeg": "audio/mp3",
    "audio/x-aiff": "audio/aiff",
    "audio/x-flac": "audio/flac",
    "video/quicktime": "video/mov",
    "video/x-msvideo": "video/avi",
}

_MEDIA_PREFIXES = ("image/", "audio/", "video/")
# documents the multimodal model reads natively (Gemini understands PDFs as a
# document modality — text, layout, and any scanned/image pages)
_DOCUMENT_MIMES = ("application/pdf",)


def _is_supported(mime: str) -> bool:
    """True for a mime the multimodal model can read inline: image/audio/video, or a PDF."""
    return mime.startswith(_MEDIA_PREFIXES) or mime in _DOCUMENT_MIMES


def _canonical_mime(mime: str) -> str:
    return _MIME_ALIASES.get(mime, mime)


async def _media(env: ExpertEnv) -> tuple[list[tuple[bytes, str]], list[tuple[str, int]]]:
    """Gather the attached media from the workspace it was seeded into.

    Returns (media, oversized): `media` is [(bytes, canonical-mime)] for files within the
    inline limit; `oversized` is [(name, size)] for files skipped because they exceed the
    limit (reported to the user instead of 400-ing the multimodal call). Files that are
    neither media nor a supported document (PDF) are ignored; an unreadable file is
    skipped rather than sinking the run."""
    workspace = getattr(env, "workspace", None)
    if workspace is None:
        return [], []
    media: list[tuple[bytes, str]] = []
    oversized: list[tuple[str, int]] = []
    for name in getattr(env, "input_files", None) or []:
        mime = mimetypes.guess_type(name)[0] or ""
        if not _is_supported(mime):
            continue
        try:
            data = await workspace.read_bytes(name)
        except Exception:  # noqa: BLE001 — a single unreadable file must not sink the run
            continue
        if len(data) > _INLINE_LIMIT_BYTES:
            oversized.append((name, len(data)))
        else:
            media.append((data, _canonical_mime(mime)))
    return media, oversized
