"""Media expert (key: media.analyst) — understands attached media (images, audio,
video). It reads the media seeded into its workspace and reasons over it with a
multimodal model (Gemini by default): describes images and reads their text (OCR),
transcribes and summarizes audio, and describes/summarizes video. Its behavior lives
in its system prompt + skills beside this file; this module declares what it is and
how its request + the attached media become the agent's multimodal task.

Note: media rides INLINE in the model request, so a single very large file (tens of
MB) can exceed the provider's inline limit and that one call fails gracefully; a
File-API upload path for big video is a later enhancement."""

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
        description="What to do with the attached media: describe an image and read its "
        "text (OCR), transcribe or summarize audio, describe or summarize video, or answer "
        "a question about the media's content."
    )


@expert
class MediaExpert:
    name = "analyst"
    domain = "media"
    description = (
        "Understand attached media (images, audio, video) with a multimodal model: describe "
        "images and read their text (OCR), transcribe and summarize audio, describe and "
        "summarize video, and answer questions about the content."
    )
    input_schema = MediaIn
    output_schema = ExpertOutput
    skills = ("skills",)                # baseline skills/ beside this file
    tools = ("fs.read",)               # grants a per-run workspace so attached media are seeded + readable
    model_role = "media_expert"        # multimodal understanding, Gemini by default
    permission = PermissionLevel.READ
    tags = ("media", "image", "audio", "video", "vision", "transcription")

    async def run(self, args: MediaIn, env: ExpertEnv) -> ExpertOutput:
        return await think(env, _task(args, env), media=await _media(env))


def _task(args: MediaIn, env: ExpertEnv) -> str:
    """This expert's per-call task: the request itself; the media rides as multimodal input."""
    return args.prompt


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


def _canonical_mime(mime: str) -> str:
    return _MIME_ALIASES.get(mime, mime)


async def _media(env: ExpertEnv) -> list[tuple[bytes, str]]:
    """The attached media (image/audio/video) as (bytes, canonical-mime) pairs, read
    from the workspace they were seeded into. Non-media inputs are ignored. Best-effort:
    an unreadable file is skipped rather than sinking the run."""
    workspace = getattr(env, "workspace", None)
    if workspace is None:
        return []
    out: list[tuple[bytes, str]] = []
    for name in getattr(env, "input_files", None) or []:
        mime = mimetypes.guess_type(name)[0] or ""
        if not mime.startswith(_MEDIA_PREFIXES):
            continue
        try:
            out.append((await workspace.read_bytes(name), _canonical_mime(mime)))
        except Exception:  # noqa: BLE001 — a single unreadable file must not sink the run
            continue
    return out
