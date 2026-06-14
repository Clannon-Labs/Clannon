"""Media expert (image-first): media is folded into the user message as
BinaryContent for a multimodal model, and the expert gathers only image inputs."""

import asyncio

from pydantic_ai import BinaryContent

from core.llm.framework import AgentHandle, run_structured
from experts.media.expert import MediaExpert, _images
from registry.capabilities import CapabilityKind, discover, registry
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


def test_images_gathers_only_image_files():
    ws = _WS({"logo.png": b"PNGBYTES", "notes.txt": b"hi", "chart.jpg": b"JPGBYTES"})
    env = _env(ws, ["logo.png", "notes.txt", "chart.jpg"])
    got = asyncio.run(_images(env))
    assert sorted((m, d) for d, m in got) == [("image/jpeg", b"JPGBYTES"), ("image/png", b"PNGBYTES")]


def test_images_empty_without_workspace_or_images():
    assert asyncio.run(_images(_env(None, ["logo.png"]))) == []        # no workspace
    ws = _WS({"notes.txt": b"hi"})
    assert asyncio.run(_images(_env(ws, ["notes.txt"]))) == []          # no images among inputs


# ---- it self-registers, ready for the orchestrator -------------------------


def test_media_expert_is_registered_and_healthy():
    discover()
    spec = registry.get_expert("media.analyst")
    assert spec is not None and spec.model_role == "media_expert"
    assert "fs.read" in spec.tool_grants                 # gets a workspace so images seed
    assert "media.analyst" not in {b.key for b in registry.broken()}
