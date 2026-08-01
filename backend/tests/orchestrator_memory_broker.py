"""Memory Manager stays sole broker; model gets one bounded delete command."""

import asyncio
from types import SimpleNamespace

from pathlib import Path

from foundation import HydrationPackage, MemoryItem, MemoryStore, NormalizedInput, VrakshaContext
from core.orchestrator.utils.prompt import build_user_prompt
from registry.capabilities import CapabilityKind, discover, registry
from registry.capabilities.handler import Capabilities
from registry.capabilities.handler.native_memory import build_forget_memory_tool
from registry.capabilities.handler.support import OrchestratorDeps


def _orchestrator_tool_keys():
    """The tool keys the gateway offers the orchestrator natively — every registered
    tool minus workspace-scoped ones (mirrors Capabilities.run_turn's selection)."""
    discover()
    specs = [registry.get_tool(c["key"]) for c in registry.cards(CapabilityKind.TOOL)]
    return {s.key for s in specs if s and not getattr(s.impl, "wants_workspace", False)}


def test_no_general_memory_tool_is_registered_for_the_orchestrator():
    assert not any(key.startswith("memory.") for key in _orchestrator_tool_keys())


def test_no_expert_holds_a_memory_grant():
    # Experts are stateless. Relevant context is prepared before orchestration.
    discover()
    for card in registry.cards(CapabilityKind.EXPERT):
        spec = registry.get_expert(card["key"])
        grants = tuple(getattr(spec, "tool_grants", ()) or ())
        assert not any(g.startswith("memory.") for g in grants), (
            f"expert {spec.key!r} holds a memory grant {grants!r} — sole-broker violated"
        )


def test_baseline_prompt_requires_confirmed_delete_and_forbids_guessed_ids():
    text = (Path(__file__).parent.parent / "prompts" / "orchestrator" / "system.md").read_text()
    assert "`forget_memory(memory_id)`" in text
    assert "Never guess an id" in text
    assert "Never claim memory was removed unless command returns `deleted: true`" in text
    assert "memory.search" not in text
    assert "remember(" not in text


def test_prepared_context_exposes_only_inferred_deletion_handles():
    prompt = build_user_prompt(
        NormalizedInput(modality="text", content_type="text/plain", content="forget it"),
        HydrationPackage(items=[
            MemoryItem(memory_id="learned-1", store=MemoryStore.SEMANTIC, content="learned"),
            MemoryItem(memory_id="wiki-1", store=MemoryStore.WIKI, content="user wiki"),
        ]),
    )

    assert "memory_id=learned-1" in prompt
    assert prompt.count("memory_id=") == 1


class _MemoryDeleteDouble:
    def __init__(self, *, result=True):
        self.result = result
        self.calls = []

    async def delete_entry(self, user_id, memory_id):
        self.calls.append((user_id, memory_id))
        return self.result


def _ctx(memory_id="owned"):
    ctx = VrakshaContext.new("session-1", user_id="user-1")
    ctx.hydration_items = [
        MemoryItem(
            memory_id=memory_id,
            store=MemoryStore.SEMANTIC,
            content="A relevant learned preference.",
        )
    ]
    return ctx


def _call_forget(ctx, memory, memory_id):
    tool = build_forget_memory_tool()
    deps = OrchestratorDeps(ctx=ctx, tools=None, experts=None, memory=memory)
    return asyncio.run(tool(SimpleNamespace(deps=deps), memory_id))


def test_forget_memory_deletes_only_visible_owner_scoped_id():
    ctx = _ctx()
    memory = _MemoryDeleteDouble()

    result = _call_forget(ctx, memory, "owned")

    assert result == {"deleted": True, "message": "Memory removed."}
    assert memory.calls == [("user-1", "owned")]
    assert ctx.hydration_items == []
    assert ctx.tool_calls[-1].tool_name == "forget_memory"
    assert ctx.tool_calls[-1].success is True


def test_forget_memory_refuses_guessed_id_without_touching_manager():
    ctx = _ctx()
    memory = _MemoryDeleteDouble()

    result = _call_forget(ctx, memory, "foreign-or-guessed")

    assert result["deleted"] is False
    assert memory.calls == []
    assert ctx.tool_calls[-1].success is False


def test_forget_memory_refuses_wiki_id_even_if_context_is_malformed():
    ctx = _ctx()
    ctx.hydration_items.append(MemoryItem(
        memory_id="wiki-1",
        store=MemoryStore.WIKI,
        content="User-authored wiki entry.",
    ))
    memory = _MemoryDeleteDouble()

    result = _call_forget(ctx, memory, "wiki-1")

    assert result["deleted"] is False
    assert memory.calls == []


def test_forget_memory_never_reports_success_when_manager_refuses():
    ctx = _ctx()
    memory = _MemoryDeleteDouble(result=False)

    result = _call_forget(ctx, memory, "owned")

    assert result["deleted"] is False
    assert "Do not tell user" in result["instruction"]
    assert memory.calls == [("user-1", "owned")]
    assert len(ctx.hydration_items) == 1


def test_forget_memory_is_central_only_and_gated_by_memory_port():
    from pydantic_ai.models.test import TestModel
    from core.orchestrator.schemas import OrchestratorAnswer

    discover()
    with_memory = Capabilities.open(_ctx(), memory=_MemoryDeleteDouble())
    model = TestModel(call_tools=[])
    asyncio.run(with_memory.run_turn(
        system_prompt="orchestrate",
        user_prompt="x",
        output_type=OrchestratorAnswer,
        model=model,
    ))
    assert "forget_memory" in {
        tool.name for tool in model.last_model_request_parameters.function_tools
    }

    without_memory = Capabilities.open(_ctx())
    model_without = TestModel(call_tools=[])
    asyncio.run(without_memory.run_turn(
        system_prompt="orchestrate",
        user_prompt="x",
        output_type=OrchestratorAnswer,
        model=model_without,
    ))
    assert "forget_memory" not in {
        tool.name for tool in model_without.last_model_request_parameters.function_tools
    }

    scoped = Capabilities.scoped_to(
        _ctx(), expert_keys=set(), tool_keys=set(), grants=frozenset()
    )
    assert scoped._memory is None


def test_native_model_call_reaches_manager_and_then_answers():
    from pydantic_ai import ModelResponse
    from pydantic_ai.messages import ToolCallPart
    from pydantic_ai.models.function import FunctionModel
    from core.orchestrator.schemas import OrchestratorAnswer

    ctx = _ctx()
    memory = _MemoryDeleteDouble()
    caps = Capabilities.open(ctx, memory=memory)
    calls = {"count": 0}

    def model(messages, info):
        calls["count"] += 1
        if calls["count"] == 1:
            return ModelResponse(parts=[ToolCallPart(
                tool_name="forget_memory",
                args={"memory_id": "owned"},
            )])
        output = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(
            tool_name=output.name,
            args={
                "answer_text": "I removed it from memory.",
                "presentation": "chat",
                "confidence": 1.0,
            },
        )])

    answer = asyncio.run(caps.run_turn(
        system_prompt="Use forget_memory and report only its result.",
        user_prompt="Forget the relevant memory.",
        output_type=OrchestratorAnswer,
        model=FunctionModel(model),
    ))

    assert answer.answer_text == "I removed it from memory."
    assert memory.calls == [("user-1", "owned")]
    assert ctx.tool_calls[-1].success is True
