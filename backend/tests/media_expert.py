"""Media expert (image-first): media is folded into the user message as
BinaryContent for a multimodal model, and the expert gathers only image inputs."""

import asyncio

from pydantic_ai import BinaryContent

from core.llm.framework import AgentHandle, run_structured
from experts.media.expert import _canonical_mime, _gather
from registry.capabilities import discover, registry
from registry.capabilities.handler.support import ExpertEnv, SkillBook


class _Result:
    def __init__(self, output):
        self.output = output


class _CaptureAgent:
    """Stand-in agent that records the user prompt run_structured hands it."""
    def __init__(self):
        self.received = None
    async def run(self, *args, **kwargs):
        self.received = args[0] if args else None
        return _Result("ok")


# ---- the LLM boundary folds media into the user message --------------------


def test_media_is_folded_into_user_prompt_as_binary_content():
    agent = _CaptureAgent()
    handle = AgentHandle(agent, "media_expert")
    asyncio.run(run_structured(handle, "describe this", media=[(b"\x89PNGdata", "image/png")]))
    rec = agent.received
    assert isinstance(rec, list)                       # [text, BinaryContent]
    assert rec[0] == "describe this"
    assert isinstance(rec[1], BinaryContent)
    assert rec[1].media_type == "image/png" and rec[1].data == b"\x89PNGdata"


def test_no_media_keeps_a_plain_string_prompt():
    agent = _CaptureAgent()
    handle = AgentHandle(agent, "media_expert")
    asyncio.run(run_structured(handle, "just text"))
    assert agent.received == "just text"               # bare string, not a list


def test_multiple_images_all_ride_along():
    agent = _CaptureAgent()
    handle = AgentHandle(agent, "media_expert")
    asyncio.run(run_structured(handle, "compare", media=[(b"a", "image/png"), (b"b", "image/jpeg")]))
    rec = agent.received
    assert len(rec) == 3 and [c.media_type for c in rec[1:]] == ["image/png", "image/jpeg"]


# ---- the expert gathers only image inputs from its workspace ---------------


class _WS:
    def __init__(self, files):
        self._f = files
    async def read_bytes(self, name):
        return self._f[name]


def _env(ws, seeded_names):
    env = ExpertEnv(module_dir=None, model_role="media_expert", skills=SkillBook("/", ()),
                    toolbox=None, granted=[], workspace=ws)
    env.input_files = list(seeded_names)               # what _seed_inputs records
    return env


def test_media_gathers_image_audio_video_with_canonical_mime():
    # an unparseable "pdf" (fake bytes) can't be text-extracted, so it falls through to
    # the multimodal path like the other media; nothing oversized; no docs extracted
    ws = _WS({"logo.png": b"PNG", "notes.txt": b"hi", "talk.wav": b"WAV",
              "clip.mp4": b"MP4", "report.pdf": b"%PDF-1.7"})
    env = _env(ws, ["logo.png", "notes.txt", "talk.wav", "clip.mp4", "report.pdf"])
    media, docs, oversized = asyncio.run(_gather(env))
    got = dict((m, d) for d, m in media)
    assert got == {"image/png": b"PNG", "audio/wav": b"WAV",
                   "video/mp4": b"MP4", "application/pdf": b"%PDF-1.7"}
    assert docs == [] and oversized == []


def test_media_extracts_a_text_pdf_locally_no_model_image_call():
    import fitz  # build a real one-page text PDF
    doc = fitz.open()
    doc.new_page().insert_text(
        (72, 72),
        "Clannon test document. The project codename is BLUEFERN and the launch month "
        "is October. This is a genuine text PDF used to verify local extraction.")
    pdf_bytes = doc.tobytes()
    ws = _WS({"brief.pdf": pdf_bytes})
    media, docs, oversized = asyncio.run(_gather(_env(ws, ["brief.pdf"])))
    # the PDF text was pulled LOCALLY -> goes to docs, NOT to the multimodal `media` list
    assert media == [] and oversized == []
    assert len(docs) == 1 and docs[0][0] == "brief.pdf"
    assert "BLUEFERN" in docs[0][1]
    # and _task inlines that text (clearly marked as data) for the model to reason over
    import experts.media.expert as me
    task = me._task(me.MediaIn(prompt="what is the codename?"), docs, [])
    assert "BLUEFERN" in task and "brief.pdf" in task


def test_media_skips_and_reports_oversized_files(monkeypatch):
    import experts.media.expert as me
    monkeypatch.setattr(me, "_INLINE_LIMIT_BYTES", 8)            # tiny cap for the test
    ws = _WS({"small.png": b"PNG", "big.mp4": b"x" * 64})        # big.mp4 exceeds 8 bytes
    media, docs, oversized = asyncio.run(_gather(_env(ws, ["small.png", "big.mp4"])))
    assert [m for _, m in media] == ["image/png"]               # small one included
    assert oversized == [("big.mp4", 64)]                       # big one reported, not sent
    # and the task carries an actionable note about the skipped file
    task = me._task(me.MediaIn(prompt="describe these"), docs, oversized)
    assert "big.mp4" in task and "too large" in task and "compress" in task


def test_media_returns_immediately_when_nothing_attached(monkeypatch):
    import experts.media.expert as me
    # with nothing to read, the expert must NOT call the model — doing so only
    # hallucinates and, under rate limits, burns the whole 240s expert timeout
    async def boom(*a, **k):
        raise AssertionError("think() must not run when no media is attached")
    monkeypatch.setattr(me, "think", boom)

    # a "try again" with no re-attached file: empty workspace, and a non-media file both
    for env in (_env(_WS({}), []), _env(_WS({"notes.txt": b"hi"}), ["notes.txt"])):
        out = asyncio.run(me.MediaExpert().run(me.MediaIn(prompt="what does the file say?"), env))
        assert out.confidence == 0.0
        assert "attached" in out.summary.lower()
        assert "re-attach" in out.full_content.lower()


def test_media_empty_without_workspace_or_media():
    assert asyncio.run(_gather(_env(None, ["logo.png"]))) == ([], [], [])  # no workspace
    ws = _WS({"notes.txt": b"hi"})
    assert asyncio.run(_gather(_env(ws, ["notes.txt"]))) == ([], [], [])   # no media among inputs


def test_canonical_mime_normalizes_known_aliases():
    assert _canonical_mime("audio/x-wav") == "audio/wav"
    assert _canonical_mime("audio/mpeg") == "audio/mp3"
    assert _canonical_mime("video/quicktime") == "video/mov"
    assert _canonical_mime("image/png") == "image/png"                  # pass-through unchanged


# ---- it self-registers, ready for the orchestrator -------------------------


def test_media_expert_is_registered_and_healthy():
    discover()
    spec = registry.get_expert("media.analyst")
    assert spec is not None and spec.model_role == "media_expert"
    assert "fs.read" in spec.tool_grants                 # gets a workspace so images seed
    assert "media.analyst" not in {b.key for b in registry.broken()}
