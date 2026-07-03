"""Experts receive the turn's hydrated memory PUSHED into their task (sole-broker):
the handler snapshots ctx.hydration_items into ExpertEnv, and think() folds it into
the expert's user message as labelled reference data. An expert never queries memory
itself — the Memory Manager hydrates once, the orchestrator/handler broker it."""

import asyncio

import core.llm as llm
import registry.config.prompts as prompts
from foundation import MemoryItem, MemoryStore, VrakshaContext
from registry.capabilities import ExpertOutput, discover, registry
from registry.capabilities.handler.experts import ExpertHandler
from registry.capabilities.handler.support import ExpertEnv, SkillBook, _memory_note, think


def _items():
    return [
        MemoryItem(store=MemoryStore.WIKI, content="Client Acme prefers one-page briefs", trust=3),
        MemoryItem(store=MemoryStore.SEMANTIC, content="The user's company sells solar inverters", trust=2),
    ]


def _env(tmp_path, hydration=()):
    return ExpertEnv(
        module_dir=tmp_path, model_role="research",
        skills=SkillBook(tmp_path, ()), toolbox=None, granted=[],
        hydration=list(hydration),
    )


# --- the handler snapshots the turn's hydration into the env -----------------

def test_build_env_snapshots_hydration_items():
    discover()
    spec = registry.get_expert("summary.condenser")     # no tools -> no workspace side effects
    ctx = VrakshaContext.new(session_id="s", user_id="u", trace_id="t")
    ctx.hydration_items = _items()

    env = ExpertHandler(registry=registry)._build_env(spec, ctx)

    assert env.hydration == _items()
    ctx.hydration_items.append("mutated")               # a snapshot, not a shared list
    assert len(env.hydration) == 2


def test_build_env_defaults_to_empty_hydration():
    discover()
    spec = registry.get_expert("summary.condenser")
    ctx = VrakshaContext.new(session_id="s", user_id="u", trace_id="t")
    env = ExpertHandler(registry=registry)._build_env(spec, ctx)
    assert env.hydration == []


# --- NETWORK experts get NO push (exfiltration surface under prompt injection) ---

def _ctx_with_memory():
    ctx = VrakshaContext.new(session_id="s", user_id="u", trace_id="t")
    ctx.hydration_items = _items()
    return ctx


def test_network_capable_experts_get_no_hydration_push():
    # any expert granted a NETWORK tool (outbound channel) is denied the push:
    # user memory + an outbound channel in one prompt = exfil surface
    discover()
    for key in ("delivery.notifier", "verification.claims", "web.research"):
        spec = registry.get_expert(key)
        env = ExpertHandler(registry=registry)._build_env(spec, _ctx_with_memory())
        assert env.hydration == [], f"{key} must not receive pushed memory"


def test_non_network_experts_still_get_the_push():
    discover()
    for key in ("synthesis.writer", "docs.writer", "summary.condenser"):
        spec = registry.get_expert(key)
        env = ExpertHandler(registry=registry)._build_env(spec, _ctx_with_memory())
        assert env.hydration == _items(), f"{key} should receive the pushed memory"


# --- the memory note itself ---------------------------------------------------

def test_memory_note_renders_items_as_reference_data(tmp_path):
    note = _memory_note(_env(tmp_path, _items()))
    assert "RELEVANT MEMORY" in note and "NOT instructions" in note
    assert "- (wiki) Client Acme prefers one-page briefs" in note
    assert "- (semantic) The user's company sells solar inverters" in note


def test_memory_note_empty_without_hydration(tmp_path):
    assert _memory_note(_env(tmp_path)) == ""


# --- think() folds the note into the expert's user message --------------------

def test_think_folds_hydration_into_the_user_message(tmp_path, monkeypatch):
    monkeypatch.setattr(prompts, "read_overlay_text", lambda rel, base: ("SYS", "baseline"))
    monkeypatch.setattr(llm, "build_tool_agent", lambda *a, **k: object())

    seen = []
    out = ExpertOutput(summary="ok", full_content="done", citations=[], confidence=0.9)
    async def fake_run(agent, user_prompt, **kw):
        seen.append(user_prompt)
        return out
    monkeypatch.setattr(llm, "run_structured", fake_run)

    result = asyncio.run(think(_env(tmp_path, _items()), "do the task"))

    assert result is out
    assert seen[0].startswith("do the task")            # the task comes first, memory after
    assert "- (wiki) Client Acme prefers one-page briefs" in seen[0]
    assert "NOT instructions" in seen[0]


def test_think_leaves_the_message_clean_without_hydration(tmp_path, monkeypatch):
    monkeypatch.setattr(prompts, "read_overlay_text", lambda rel, base: ("SYS", "baseline"))
    monkeypatch.setattr(llm, "build_tool_agent", lambda *a, **k: object())
    seen = []
    out = ExpertOutput(summary="ok", full_content="done", citations=[], confidence=0.9)
    async def fake_run(agent, user_prompt, **kw):
        seen.append(user_prompt)
        return out
    monkeypatch.setattr(llm, "run_structured", fake_run)

    asyncio.run(think(_env(tmp_path), "do the task"))
    assert seen[0] == "do the task"                     # no memory heading injected
