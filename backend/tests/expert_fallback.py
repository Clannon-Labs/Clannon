"""think() forces a graceful final answer when an expert hits its turn/usage cap,
mirroring the orchestrator — a thorough expert returns its best ExpertOutput
instead of failing hard."""

import asyncio

import core.llm as llm
import registry.config.prompts as prompts
from foundation import MaxRetriesExceededError
from registry.capabilities import ExpertOutput
from registry.capabilities.handler.support import ExpertEnv, SkillBook, think


def _env(tmp_path):
    return ExpertEnv(
        module_dir=tmp_path, model_role="research",
        skills=SkillBook(tmp_path, ()), toolbox=None, granted=[],
    )


def test_think_forces_final_answer_at_turn_cap(tmp_path, monkeypatch):
    # don't touch the filesystem for the system prompt
    monkeypatch.setattr(prompts, "read_overlay_text", lambda rel, base: ("SYS", "baseline"))

    built = []
    def fake_build(layer, *, output_type, system_prompt, tools, deps_type):
        built.append({"system_prompt": system_prompt, "tools": tools})
        return object()
    monkeypatch.setattr(llm, "build_tool_agent", fake_build)

    forced = ExpertOutput(summary="forced", full_content="best effort so far", citations=[], confidence=0.3)
    calls = []
    async def fake_run(agent, user_prompt, **kw):
        calls.append(kw)
        if len(calls) == 1:
            raise MaxRetriesExceededError("research hit its turn/usage cap")  # main run caps
        return forced                                                        # forced pass answers
    monkeypatch.setattr(llm, "run_structured", fake_run)

    out = asyncio.run(think(_env(tmp_path), "do the task"))

    assert out is forced and out.confidence == 0.3          # returned the forced best effort
    assert len(calls) == 2                                  # main run, then the forced fallback
    assert calls[1]["max_turns"] == 1                       # forced pass is a single turn
    assert built[1]["tools"] == []                          # tools withheld on the forced pass
    assert "tool/turn limit" in built[1]["system_prompt"]   # the force-answer nudge is appended


def test_think_returns_normally_under_cap(tmp_path, monkeypatch):
    # happy path: no cap -> first run's result is returned, no forced second pass
    monkeypatch.setattr(prompts, "read_overlay_text", lambda rel, base: ("SYS", "baseline"))
    monkeypatch.setattr(llm, "build_tool_agent", lambda *a, **k: object())
    normal = ExpertOutput(summary="ok", full_content="done", citations=[], confidence=0.9)
    calls = []
    async def fake_run(agent, user_prompt, **kw):
        calls.append(kw)
        return normal
    monkeypatch.setattr(llm, "run_structured", fake_run)

    out = asyncio.run(think(_env(tmp_path), "task"))
    assert out is normal and len(calls) == 1                # no forced fallback needed
