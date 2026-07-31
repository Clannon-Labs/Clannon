"""
End-to-end proof for the FIRST concrete batch (`engineering`, CB2 flagship) —
ratified design: proposals/archive/to-backend/2026-07-25_engineering-batch-design.md.

Drives a REAL nested run_turn through the REAL registry (`discover()`), the REAL
`backend/batches.yaml` (`registry.config.batches.load_batches`), and the REAL
`code.engineer` expert — not hand-built fakes, so this proof exercises the actual
files this design ships. Three model tiers are involved (central orchestrator ->
batch orchestrator -> code.engineer's own agent); `think()` (unlike `run_turn`)
has no `model=` override parameter, so `core.llm.framework.model_for_layer` is
patched for the duration of each test to hand every tier the same FunctionModel
spy -- the only way to reach the third tier without a production code change.

What this proves: the batch mechanism works end-to-end (spawn, scope, awareness
ACTIVE/DONE/FAILED, findings, real sandboxed tool execution) on a real registry.
It does NOT prove CB2's large-repo target (30M-line navigation) -- that's gated
on tooling that doesn't exist yet (nav/patch-apply), by design (see the ratified
proposal's §6). Docker need not be installed: `code.run`'s own workspace degrades
honestly (`[sandbox disabled/unavailable]`) rather than requiring it; this suite
only relies on `fs.write`'s pure-file-I/O path, which needs no container.

Run:
    cd backend && .venv/bin/python -m pytest tests/orchestrator_engineering_batch.py -v
"""

import asyncio
from unittest.mock import patch

from pydantic_ai import ModelResponse
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.function import FunctionModel

from foundation import BatchLifecycleStatus, CrossBatchAwareness, VrakshaContext
from registry.capabilities import discover
from registry.capabilities.handler import Capabilities
from registry.config.batches import load_batches
from registry.config.prompts import get_prompt
from core.orchestrator.schemas import OrchestratorAnswer


class _FakeAwareness:
    """Records every call it receives, in order -- the control-plane side channel
    stays fake (matches tests/orchestrator_batch_handler.py); what's real here is
    the registry, the batch config, and the expert."""

    def __init__(self):
        self._awareness = CrossBatchAwareness()
        self.record_calls: list[tuple] = []

    async def record_batch_status(self, user_id, mission_id, batch_id, domain, status, headline):
        self.record_calls.append((user_id, mission_id, batch_id, domain, status, headline))
        return True

    async def cross_batch_awareness(self, user_id, mission_id, requesting_batch_id):
        return self._awareness

    @property
    def statuses(self) -> list[BatchLifecycleStatus]:
        return [call[4] for call in self.record_calls]


def _ctx() -> VrakshaContext:
    ctx = VrakshaContext.new("s-engineering-batch")
    ctx.mission_id = "m1"
    return ctx


def _caps(ctx, awareness):
    discover()
    return Capabilities.open(ctx, batch_registry=load_batches(), awareness=awareness)


def test_engineering_batch_config_loads_and_activates_spawn_batch():
    """The narrowest possible check before the deep end-to-end run: the real
    batches.yaml resolves to a BatchDefinition and flips has_batches True --
    i.e. the wiring.py change actually turns spawn_batch on."""
    ctx = _ctx()
    caps = _caps(ctx, _FakeAwareness())
    assert caps._batches.has_batches is True
    assert "engineering" in caps._batches._batch_registry
    definition = caps._batches._batch_registry["engineering"]
    assert definition.expert_keys == frozenset({"code.engineer"})
    assert definition.tool_keys == frozenset({"fs.read", "fs.write", "fs.patch", "code.run", "code.ast_search", "code.dep_graph"})
    assert definition.system_prompt == get_prompt("batch_orchestrator.engineering").text


def test_engineering_batch_end_to_end_spawns_runs_code_engineer_records_awareness():
    """Central orchestrator -> spawn_batch("engineering") -> batch's own scoped
    turn -> code.engineer expert -> code.engineer's own agent -> a real fs.write
    against a real (Docker-workspace-backed) sandbox. One shared FunctionModel
    spy plays all three tiers, dispatched by call order (deterministic single-path
    script, matching tests/orchestrator_batch_handler.py's own precedent)."""
    ctx = _ctx()
    awareness = _FakeAwareness()
    caps = _caps(ctx, awareness)
    calls = {"n": 0}

    def spy(messages, info):
        calls["n"] += 1
        if calls["n"] == 1:
            # central orchestrator: delegate to the engineering batch
            tool = next(t for t in info.function_tools if t.name == "spawn_batch")
            return ModelResponse(parts=[ToolCallPart(
                tool_name=tool.name,
                args={"batch_key": "engineering", "task": "write hello.txt containing 'hi'"},
            )])
        if calls["n"] == 2:
            # the batch's own scoped turn: delegate to its one member expert
            tool = next(t for t in info.function_tools if t.name == "code_engineer")
            return ModelResponse(parts=[ToolCallPart(
                tool_name=tool.name, args={"prompt": "write hello.txt containing 'hi'"},
            )])
        if calls["n"] == 3:
            # code.engineer's own agent: actually touch the real workspace
            tool = next(t for t in info.function_tools if t.name == "fs_write")
            return ModelResponse(parts=[ToolCallPart(
                tool_name=tool.name, args={"path": "hello.txt", "content": "hi"},
            )])
        if calls["n"] == 4:
            # code.engineer's own agent: final ExpertOutput
            out = info.output_tools[0]
            return ModelResponse(parts=[ToolCallPart(
                tool_name=out.name,
                args={"summary": "wrote hello.txt", "full_content": "hello.txt written with 'hi'", "confidence": 0.85},
            )])
        if calls["n"] == 5:
            # the batch's own turn: final OrchestratorAnswer
            out = info.output_tools[0]
            return ModelResponse(parts=[ToolCallPart(
                tool_name=out.name,
                args={"answer_text": "hello.txt written with 'hi'", "presentation": "chat", "confidence": 0.8},
            )])
        # central orchestrator: final answer
        out = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(
            tool_name=out.name,
            args={"answer_text": "done: hello.txt created", "presentation": "chat", "confidence": 0.9},
        )])

    model = FunctionModel(spy)
    with patch("core.llm.framework.model_for_layer", return_value=model):
        result = asyncio.run(caps.run_turn(
            system_prompt="orchestrate", user_prompt="engineering task", output_type=OrchestratorAnswer,
            model=model,
        ))

    assert result.answer_text == "done: hello.txt created"

    # the batch tier's two-output split: ctx.batch_findings got the full text
    assert len(ctx.batch_findings) == 1
    finding = ctx.batch_findings[0]
    assert finding.batch == "engineering"
    assert finding.full_content == "hello.txt written with 'hi'"

    # the expert tier's own two-output split, one tier further in
    assert len(ctx.expert_findings) == 1
    assert ctx.expert_findings[0].expert == "code.engineer"

    # the real fs.write call actually ran against a real (temp-dir-backed) workspace
    write_calls = [r for r in ctx.tool_calls if r.tool_name == "fs.write"]
    assert len(write_calls) == 1
    assert write_calls[0].success is True
    assert write_calls[0].result["ok"] is True

    # cross-batch awareness recorded ACTIVE then DONE, keyed on the batch's domain
    assert awareness.statuses == [BatchLifecycleStatus.ACTIVE, BatchLifecycleStatus.DONE]
    assert awareness.record_calls[0][3] == "engineering"        # domain
    assert awareness.record_calls[0][1] == "m1"                 # mission_id threaded through


def test_engineering_batch_records_failed_on_a_real_model_fault_and_central_still_answers():
    """A fault inside the batch's own nested turn (a model/provider failure) must
    still record FAILED through the real awareness port and must NOT crash the
    central orchestrator's own turn -- spawn_batch swallows the batch-level fault
    and reports it back as an unavailable summary, same contract as the fake-model
    tests in orchestrator_batch_handler.py, now proven against the real stack."""
    ctx = _ctx()
    awareness = _FakeAwareness()
    caps = _caps(ctx, awareness)
    calls = {"n": 0}

    def spy(messages, info):
        calls["n"] += 1
        if calls["n"] == 1:
            tool = next(t for t in info.function_tools if t.name == "spawn_batch")
            return ModelResponse(parts=[ToolCallPart(
                tool_name=tool.name, args={"batch_key": "engineering", "task": "do the thing"},
            )])
        if calls["n"] == 2:
            raise RuntimeError("simulated provider fault mid-batch")
        # central orchestrator's own next turn, after spawn_batch reports failure
        out = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(
            tool_name=out.name,
            args={"answer_text": "batch failed, reporting", "presentation": "chat", "confidence": 0.2},
        )])

    model = FunctionModel(spy)
    with patch("core.llm.framework.model_for_layer", return_value=model):
        result = asyncio.run(caps.run_turn(
            system_prompt="orchestrate", user_prompt="engineering task", output_type=OrchestratorAnswer,
            model=model,
        ))

    assert result.answer_text == "batch failed, reporting"      # the central turn survives
    assert ctx.batch_findings == []                              # no findings buffered on failure
    assert awareness.statuses == [BatchLifecycleStatus.ACTIVE, BatchLifecycleStatus.FAILED]


def test_engineering_batch_code_engineer_reads_a_slice_and_patches_it():
    """The nav/patch-tooling design's acceptance criterion: code.engineer can read
    a precise line range and patch it, inside the batch, through the real registry
    -- not just fs.write from scratch. Seeds a file directly onto the real
    DockerWorkspace via fs.write first (call 3), then reads a range of it (call 4)
    and patches that range (call 5), proving fs.read/fs.patch are both actually
    granted inside the engineering batch (present in batches.yaml's tool_keys)."""
    ctx = _ctx()
    awareness = _FakeAwareness()
    caps = _caps(ctx, awareness)
    calls = {"n": 0}

    def spy(messages, info):
        calls["n"] += 1
        if calls["n"] == 1:
            tool = next(t for t in info.function_tools if t.name == "spawn_batch")
            return ModelResponse(parts=[ToolCallPart(
                tool_name=tool.name, args={"batch_key": "engineering", "task": "fix line 2 of a.py"},
            )])
        if calls["n"] == 2:
            tool = next(t for t in info.function_tools if t.name == "code_engineer")
            return ModelResponse(parts=[ToolCallPart(
                tool_name=tool.name, args={"prompt": "fix line 2 of a.py"},
            )])
        if calls["n"] == 3:
            tool = next(t for t in info.function_tools if t.name == "fs_write")
            return ModelResponse(parts=[ToolCallPart(
                tool_name=tool.name, args={"path": "a.py", "content": "one\ntwo\nthree\n"},
            )])
        if calls["n"] == 4:
            tool = next(t for t in info.function_tools if t.name == "fs_read")
            return ModelResponse(parts=[ToolCallPart(
                tool_name=tool.name, args={"path": "a.py", "start_line": 2, "end_line": 2},
            )])
        if calls["n"] == 5:
            tool = next(t for t in info.function_tools if t.name == "fs_patch")
            return ModelResponse(parts=[ToolCallPart(
                tool_name=tool.name, args={"path": "a.py", "start_line": 2, "end_line": 2, "replacement": "TWO"},
            )])
        if calls["n"] == 6:
            out = info.output_tools[0]
            return ModelResponse(parts=[ToolCallPart(
                tool_name=out.name, args={"summary": "patched line 2", "full_content": "patched a.py", "confidence": 0.85},
            )])
        if calls["n"] == 7:
            out = info.output_tools[0]
            return ModelResponse(parts=[ToolCallPart(
                tool_name=out.name,
                args={"answer_text": "patched a.py", "presentation": "chat", "confidence": 0.8},
            )])
        out = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(
            tool_name=out.name,
            args={"answer_text": "done: a.py patched", "presentation": "chat", "confidence": 0.9},
        )])

    model = FunctionModel(spy)
    with patch("core.llm.framework.model_for_layer", return_value=model):
        result = asyncio.run(caps.run_turn(
            system_prompt="orchestrate", user_prompt="engineering task", output_type=OrchestratorAnswer,
            model=model,
        ))

    assert result.answer_text == "done: a.py patched"
    read_calls = [r for r in ctx.tool_calls if r.tool_name == "fs.read"]
    patch_calls = [r for r in ctx.tool_calls if r.tool_name == "fs.patch"]
    assert len(read_calls) == 1 and read_calls[0].success
    assert "two" in read_calls[0].result["content"]
    assert len(patch_calls) == 1 and patch_calls[0].success and patch_calls[0].result["ok"] is True
    assert awareness.statuses == [BatchLifecycleStatus.ACTIVE, BatchLifecycleStatus.DONE]
