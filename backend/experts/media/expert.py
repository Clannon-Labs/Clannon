"""Media expert (key: media.analyst) — understands attached images. It reads the
images seeded into its workspace and reasons over them with a multimodal model
(Gemini by default): describes scenes, reads/extracts text (OCR), summarizes, and
answers questions about visual content. Its behavior lives in its system prompt +
skills beside this file; this module declares what it is and how its request + the
attached images become the agent's multimodal task. Audio/video land next."""

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
        description="What to do with the attached image(s): describe them, read/extract "
        "their text (OCR), summarize, or answer a question about their visual content."
    )


@expert
class MediaExpert:
    name = "analyst"
    domain = "media"
    description = (
        "Understand attached images with a multimodal model: describe them, read/extract "
        "their text (OCR), summarize, and answer questions about visual content."
    )
    input_schema = MediaIn
    output_schema = ExpertOutput
    skills = ("skills",)                # baseline skills/ beside this file
    tools = ("fs.read",)               # grants a per-run workspace so attached images are seeded + readable
    model_role = "media_expert"        # multimodal understanding, Gemini by default
    permission = PermissionLevel.READ
    tags = ("media", "image", "vision")

    async def run(self, args: MediaIn, env: ExpertEnv) -> ExpertOutput:
        return await think(env, _task(args, env), media=await _images(env))


def _task(args: MediaIn, env: ExpertEnv) -> str:
    """This expert's per-call task: the request itself; the images ride as multimodal media."""
    return args.prompt


async def _images(env: ExpertEnv) -> list[tuple[bytes, str]]:
    """The attached images as (bytes, mime) pairs, read from the workspace they were
    seeded into. Non-image inputs are ignored. Best-effort: an unreadable file is skipped."""
    workspace = getattr(env, "workspace", None)
    if workspace is None:
        return []
    out: list[tuple[bytes, str]] = []
    for name in getattr(env, "input_files", None) or []:
        mime = mimetypes.guess_type(name)[0] or ""
        if not mime.startswith("image/"):
            continue
        try:
            out.append((await workspace.read_bytes(name), mime))
        except Exception:  # noqa: BLE001 — a single unreadable image must not sink the run
            continue
    return out
