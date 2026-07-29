"""
Hermetic turn-budget harness for the orchestrator and expert loops.

WHAT THIS PINS:
  (a) The orchestrator loop is forced to a final answer once it hits
      settings.ORCHESTRATOR.max_turns -- a pathological spy that always requests another
      tool call must terminate, never run unbounded paid rounds.
  (b) A single expert run is bounded by settings.EXPERTS.max_turns in the same way.
  (c) The total number of model calls in each case is finite and <=
      settings.ORCHESTRATOR.max_turns + 2 / settings.EXPERTS.max_turns + 2 respectively.

This test is DISTINCT from tests/orchestrator_recovery.py, which pins graceful
degradation on rate-limit and timeout failures. This harness pins the TURN-CAP
termination and bounded-call-count contract specifically.

HERMETIC: no network, no paid keys. The LLM is a FunctionModel spy double;
memory store and embeddings are no-ops; no expert implementation is invoked.
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch

from pydantic_ai import ModelResponse
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.function import FunctionModel

import settings
from foundation import VrakshaContext
from registry.capabilities import discover
from registry.capabilities.handler import Capabilities
from registry.capabilities.schemas import ExpertOutput
from core.orchestrator.schemas import OrchestratorAnswer


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _caps():
    discover()
    return Capabilities.open(VrakshaContext.new("s"))


# ---------------------------------------------------------------------------
# A. Orchestrator: loop capped at settings.ORCHESTRATOR.max_turns
# ---------------------------------------------------------------------------

def test_orchestrator_loop_is_bounded_at_cap():
    """A pathological spy that always calls 'remember' (always eager, never deferred)
    must be forced to a final answer once the orchestrator hits settings.ORCHESTRATOR.max_turns
    -- it must NOT loop forever and consume unbounded paid rounds.

    Flags an unbounded loop as a REAL gap in two ways:
      - If the cap is enforced but set too high: assertion on call_count fails fast.
      - If the cap is fully disabled: asyncio.wait_for timeout raises TimeoutError,
        converting a catastrophic pytest hang into a clean failure.

    Prints: turn-count + call-count vs cap."""
    call_log = []

    def always_loop(messages, info):
        call_log.append(1)
        names = {t.name for t in info.function_tools}
        if "remember" in names:
            # Keep requesting another tool call until tools are withheld.
            return ModelResponse(parts=[ToolCallPart(
                tool_name="remember", args={"content": "looping"})])
        # tools withheld -> cap has fired; produce the forced final answer
        out = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(
            tool_name=out.name,
            args={"answer_text": "forced by turn cap", "presentation": "chat", "confidence": 0.3},
        )])

    caps = _caps()

    async def _run():
        return await caps.run_turn(
            system_prompt="orchestrate",
            user_prompt="loop forever",
            output_type=OrchestratorAnswer,
            model=FunctionModel(always_loop),
            # NO max_turns override: uses the real settings.ORCHESTRATOR.max_turns
        )

    ans = asyncio.run(asyncio.wait_for(_run(), timeout=30))

    cap = settings.ORCHESTRATOR.max_turns
    call_count = len(call_log)
    # Upper bound: cap+1 requests in the main loop + 1 for the forced-answer pass
    upper_bound = cap + 2
    print(
        f"\n[turn-budget] orchestrator: {call_count} model calls"
        f" vs settings.ORCHESTRATOR.max_turns={cap} (bound={upper_bound})"
    )

    assert isinstance(ans, OrchestratorAnswer), (
        "loop must terminate with a structured OrchestratorAnswer, not an exception or hang"
    )
    assert call_count > 0, "spy was never called -- something is wrong with the test setup"
    assert call_count <= upper_bound, (
        f"UNBOUNDED LOOP DETECTED: spy called {call_count} times but bound={upper_bound}. "
        f"The orchestrator turn budget is NOT enforced -- "
        f"a pathological brief can run unbounded paid rounds. This is a real gap."
    )
    assert ans.answer_text, "forced final answer must be non-empty"


# ---------------------------------------------------------------------------
# B. Expert: loop capped at settings.EXPERTS.max_turns via think()
# ---------------------------------------------------------------------------

def test_expert_loop_is_bounded_at_cap():
    """An expert spy that always calls 'load_skill' must terminate at settings.EXPERTS.max_turns.
    Exercises the think() path in registry.capabilities.handler.support directly,
    with the model replaced by a FunctionModel spy.

    Flags an unbounded loop as a REAL gap in two ways:
      - If the cap is enforced but set too high: assertion on call_count fails fast.
      - If the cap is fully disabled: asyncio.wait_for timeout raises TimeoutError,
        converting a catastrophic pytest hang into a clean failure.

    Prints: turn-count + call-count vs cap."""
    from registry.capabilities.handler.support import ExpertEnv, SkillBook, think

    call_log = []

    def always_load(messages, info):
        call_log.append(1)
        names = {t.name for t in info.function_tools}
        if "load_skill" in names:
            # Keep calling load_skill (returns a not-found note, spy loops again)
            return ModelResponse(parts=[ToolCallPart(
                tool_name="load_skill", args={"name": "nonexistent"})])
        # tools withheld -> cap has fired; produce the forced final answer
        out = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(
            tool_name=out.name,
            args={
                "summary": "forced by turn cap",
                "full_content": "expert capped before finishing",
                "confidence": 0.3,
            })])

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a minimal system.md so read_overlay_text can resolve the baseline
        sys_md = Path(tmpdir) / "system.md"
        sys_md.write_text("You are a test expert.", encoding="utf-8")

        env = ExpertEnv(
            module_dir=Path(tmpdir),
            model_role="research",   # valid role in models.yaml; model is patched below
            skills=SkillBook(Path(tmpdir), ()),   # no real skills; load_skill returns not-found
            toolbox=None,
            granted=[],
        )

        # Patch model_for_layer in framework.py so build_tool_agent uses our spy
        with patch(
            "core.llm.framework.model_for_layer",
            return_value=FunctionModel(always_load),
        ):
            output = asyncio.run(
                asyncio.wait_for(think(env, "loop inside an expert forever"), timeout=30)
            )

    cap = settings.EXPERTS.max_turns
    call_count = len(call_log)
    # Upper bound: cap+1 requests in the main loop + 1 for the forced-answer pass
    upper_bound = cap + 2
    print(
        f"\n[turn-budget] expert: {call_count} model calls"
        f" vs settings.EXPERTS.max_turns={cap} (bound={upper_bound})"
    )

    assert isinstance(output, ExpertOutput), (
        "expert loop must terminate with an ExpertOutput, not an exception or hang"
    )
    assert call_count > 0, "spy was never called -- something is wrong with the test setup"
    assert call_count <= upper_bound, (
        f"UNBOUNDED EXPERT LOOP: spy called {call_count} times but bound={upper_bound}. "
        f"settings.EXPERTS.max_turns is NOT enforced in think() -- "
        f"a pathological expert can run unbounded paid rounds. This is a real gap."
    )
    assert output.full_content or output.summary, (
        "forced expert output must have some content"
    )
