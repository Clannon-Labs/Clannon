"""Static contract for central and batch orchestrator prompts.

These assertions are intentionally discriminating: routing must come from
explicit presentation intent, not from weak-model tool choice or answer shape.
"""

import asyncio
import re
from pathlib import Path

import yaml
from pydantic_ai import ModelResponse
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.function import FunctionModel

from foundation import VrakshaContext
from registry.capabilities import CapabilityKind, discover, registry
from registry.capabilities.handler import BatchDefinition, Capabilities
from registry.config.batches import _load_batches
from registry.config.prompts import Prompt, PromptRegistry

from core.orchestrator.schemas import OrchestratorAnswer


BACKEND = Path(__file__).resolve().parents[1]
PROMPTS = BACKEND / "prompts"
OVERLAY = BACKEND / "prompts.secure"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _model_prompt(relative: str) -> str:
    """Compose the exact overlay-first role + about text for an about:true prompt.

    A minimal composition avoids loading unrelated registry entries, so another
    prompt domain under active development cannot make this contract test lie
    about the orchestrator surface it owns.
    """
    role = OVERLAY / relative
    if not role.exists():
        role = PROMPTS / relative
    about = OVERLAY / "about_clannon.md"
    if not about.exists():
        about = PROMPTS / "about_clannon.md"
    return f"{_read(about).strip()}\n\n---\n\n{_read(role).strip()}"


def _engineering_definition() -> BatchDefinition:
    prompt = _model_prompt("batches/engineering/orchestrator/system.md")
    prompts = PromptRegistry({
        "batch_orchestrator.engineering": Prompt(
            name="batch_orchestrator.engineering",
            version=3,
            text=prompt,
            locked=False,
            source="test-composed",
        ),
    })
    return _load_batches(BACKEND / "batches.yaml", prompt_registry=prompts)["engineering"]


def _capture_model_tools(caps: Capabilities, prompt: str, *, with_message_sink=False) -> set[str]:
    """Run one hermetic model turn and return exact function names it received."""
    seen: set[str] = set()

    def model(_messages, info):
        seen.update(tool.name for tool in info.function_tools)
        output = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(
            tool_name=output.name,
            args={
                "answer_text": "done",
                "presentation": "chat",
                "confidence": 1.0,
                "deliverable_ref": "",
            },
        )])

    async def on_message(_text: str) -> None:
        return None

    asyncio.run(caps.run_turn(
        system_prompt=prompt,
        user_prompt="answer directly",
        output_type=OrchestratorAnswer,
        model=FunctionModel(model),
        on_message=on_message if with_message_sink else None,
    ))
    return seen


def test_orchestrator_prompts_are_clannon_only_with_no_copied_provider_identity():
    central = _read(PROMPTS / "orchestrator" / "system.md")
    batch = _read(PROMPTS / "batches" / "engineering" / "orchestrator" / "system.md")
    assert "You are Clannon" in central
    assert "answer as Clannon" in central
    assert "one short sentence\n(25 words maximum)" in central
    assert "Do not explain features, architecture, tools, or workflow" in central
    assert "Do not append a generic “How can I help?” question." in central
    assert "Clannon Engineering Batch Orchestrator" in batch
    forbidden = ("claude", "anthropic", "fable", "openai", "chatgpt", "{antml", "/home/claude")
    for text in (central, batch):
        assert not any(token in text.lower() for token in forbidden)


def test_central_prompt_pins_exact_four_field_output_contract():
    text = _read(PROMPTS / "orchestrator" / "system.md")
    contract = text.split("<!-- CONTRACT_FIELDS_START -->", 1)[1].split(
        "<!-- CONTRACT_FIELDS_END -->", 1
    )[0]
    fields = re.findall(r"^  ([a-z_]+):", contract, flags=re.MULTILINE)
    assert fields == ["answer_text", "presentation", "confidence", "deliverable_ref"]
    assert "exactly four fields and no others" in text


def test_central_prompt_makes_say_sparse_live_commentary_not_quick_answer():
    text = _read(PROMPTS / "orchestrator" / "system.md")
    assert "`say()` is live commentary, never the answer" in text
    assert "before spawning experts or batches" in text
    assert "Do not call `say()` for a direct, quick, casual, ordinary, or technical answer." in text
    assert "`say()` is never the final answer" in text
    assert "Calling `say()` does not make the final answer a report." in text


def test_central_prompt_pins_presentation_non_heuristics_and_artifact_rules():
    text = _read(PROMPTS / "orchestrator" / "system.md")
    assert '`presentation: "chat"` means' in text
    assert '`presentation: "report"` means' in text
    for discriminator in (
        "response length",
        "Markdown",
        "technical depth",
        "tools, experts, batches",
        "generated files",
        "`finding_ref` or `deliverable_ref`",
        "whether `say()` was called",
        "task duration",
    ):
        assert discriminator in text
    assert "file is still an\nartifact, not automatically an inline report sheet" in text
    assert "resolves the full buffered artifact only in\nreport mode" in text
    assert re.search(
        r"A\s+`deliverable_ref` on a chat answer does not replace `answer_text`\.", text
    )


def test_central_prompt_contains_all_discriminating_examples():
    text = _read(PROMPTS / "orchestrator" / "system.md")
    for heading in (
        '### 1. “Who are you?”',
        "### 2. Long technical chat",
        "### 3. Long work, commentary, final chat",
        "### 4. Explicit inline report",
        "### 5. Generated file",
        "### 6. Report artifact",
        "### 7. Weak-model anti-pattern: quick answer through `say()`",
    ):
        assert heading in text
    weak_model = text.split("### 7. Weak-model anti-pattern", 1)[1]
    assert "Wrong: call `say()`" in weak_model
    assert 'presentation: "chat"' in weak_model


def test_batch_prompt_is_scoped_internal_and_forces_internal_chat_shape():
    text = _read(PROMPTS / "batches" / "engineering" / "orchestrator" / "system.md")
    assert "Clannon Engineering Batch Orchestrator" in text
    assert "one\ndelegated engineering sub-task" in text
    assert "Use only the tool and expert schemas granted to this batch." in text
    assert "Do not call `say()`" in text
    assert "memory" not in text.lower()
    assert "Do not spawn another batch." in text
    assert "Complete the work this turn." in text
    assert '`presentation` is always `"chat"`' in text
    assert "`deliverable_ref` is always the empty string" in text
    assert 'presentation: "chat"' in text
    assert 'deliverable_ref: ""' in text
    contract = text.split("## Exact output", 1)[1].split("```", 2)[1]
    fields = re.findall(r"^  ([a-z_]+):", contract, flags=re.MULTILINE)
    assert fields == ["answer_text", "presentation", "confidence", "deliverable_ref"]


def test_registry_declares_central_v7_and_batch_v3_prompts():
    manifest = yaml.safe_load(_read(PROMPTS / "registry.yaml"))
    assert manifest["orchestrator"] == {
        "version": 7,
        "file": "orchestrator/system.md",
        "locked": False,
        "about": True,
    }
    # v2 + about:true (2026-08-01) — a batch orchestrator IS Clannon working in one
    # domain, so it composes the same identity block as the central orchestrator
    # instead of speaking as a separate agent. Deliberately NOT set on
    # verifier/filter: those judge text, they do not speak as Clannon.
    assert manifest["batch_orchestrator.engineering"] == {
        "version": 3,
        "file": "batches/engineering/orchestrator/system.md",
        "locked": False,
        "about": True,
    }


def test_active_local_overlays_match_committed_prompt_behavior_when_present():
    """The overlay may differ in WORDING from the committed baseline — that is the
    whole point of a hardened overlay, and the production copy is deliberately
    stronger. What it may never do is drop an identity invariant the baseline
    establishes.

    This asserted byte-equality until 2026-08-01, which contradicted its own name:
    any real hardening turned it red, so the only way to keep it green was to stop
    hardening. Same shape as the CB5 over-claim — a check that does not test what it
    says it tests. It now pins the BEHAVIOUR, so a stronger overlay passes and a
    WEAKER one (one that forgets it is Clannon, or starts naming a provider) fails.
    """
    forbidden_providers = ("anthropic", "openai", "google deepmind")
    for relative in ("orchestrator/system.md", "batches/engineering/orchestrator/system.md"):
        baseline = PROMPTS / relative
        overlay = OVERLAY / relative
        if not overlay.exists():
            continue
        text = _read(overlay)
        lowered = text.lower()

        base = _read(baseline).lower()

        assert "clannon" in lowered, f"{relative}: overlay lost the Clannon identity"

        # Each invariant is DERIVED from the baseline rather than hardcoded here: if
        # the committed prompt establishes a rule, the overlay must still establish
        # it. A prompt that never made a claim is not required to start making it, so
        # this stays honest for the batch prompt, which takes its identity from the
        # composed `about` block rather than from its own file.
        for invariant in ("underlying model", "answer as clannon"):
            if invariant in base:
                assert invariant in lowered, (
                    f"{relative}: overlay dropped the baseline rule {invariant!r}"
                )

        # An overlay must never NAME a provider as the builder. Mentioning one inside
        # a denial is fine, so this looks for the affirmative shape only.
        for provider in forbidden_providers:
            assert f"built by {provider}" not in lowered, (
                f"{relative}: overlay claims it is built by {provider}"
            )


def test_model_facing_central_prompt_covers_every_offered_capability_and_boundary():
    """Registry growth must update the prompt contract in the same change.

    The model spy observes the actual native-function surface, including gated
    batch/mission/memory tools. This catches a prompt that merely lists a stale
    hand-maintained roster while runtime offers something else.
    """
    discover()
    prompt = _model_prompt("orchestrator/system.md")
    caps = Capabilities.open(
        VrakshaContext.new("prompt-contract"),
        batch_registry={"engineering": _engineering_definition()},
        graph=object(),
        budget=object(),
        memory=object(),
    )
    offered = _capture_model_tools(caps, prompt, with_message_sink=True)

    direct_tools = {
        card["key"].replace(".", "_")
        for card in registry.cards(CapabilityKind.TOOL)
        if not getattr(registry.get_tool(card["key"]).impl, "wants_workspace", False)
    }
    experts = {
        card["key"].replace(".", "_")
        for card in registry.cards(CapabilityKind.EXPERT)
    }
    native = {
        "recall", "say", "spawn_batch", "start_mission", "advance_mission",
        "end_mission", "forget_memory",
    }
    assert offered == direct_tools | experts | native
    for name in offered:
        documented = f"`{name}`" in prompt or f"`{name}(" in prompt
        assert documented, f"model-facing prompt omits callable {name!r}"

    workspace_tools = {
        card["key"].replace(".", "_")
        for card in registry.cards(CapabilityKind.TOOL)
        if getattr(registry.get_tool(card["key"]).impl, "wants_workspace", False)
    }
    assert offered.isdisjoint(workspace_tools)
    for name in workspace_tools:
        assert f"`{name}`" in prompt, f"prompt omits delegated workspace capability {name!r}"
    assert "not direct central-orchestrator tools" in prompt
    assert "Any missing,\nreordered, renamed, unsupported, or false verdict" in prompt


def test_model_facing_central_prompt_pins_proven_call_stopping_rules():
    prompt = _model_prompt("orchestrator/system.md")
    assert "A successful result that satisfies the request is a stopping condition." in prompt
    assert "paraphrasing the same query is not new evidence" in prompt
    assert "implement, test,\nand write that document in one call" in prompt
    assert "Do not add `docs_writer` as a serial styling\npass" in prompt
    assert "Research plus synthesis is a\nreal dependency" in prompt


def test_model_facing_engineering_batch_matches_its_real_scoped_surface():
    """Batch coordinator sees only recall + code expert; workspace tools stay
    behind that expert while still being explained as its exact member grants.
    """
    discover()
    definition = _engineering_definition()
    caps = Capabilities.scoped_to(
        VrakshaContext.new("engineering-prompt-contract"),
        expert_keys=definition.expert_keys,
        tool_keys=definition.tool_keys,
        grants=definition.grants,
        graph=object(),
    )
    offered = _capture_model_tools(caps, definition.system_prompt)

    assert offered == {"recall", "code_engineer"}
    for name in offered:
        documented = (
            f"`{name}`" in definition.system_prompt
            or f"`{name}(" in definition.system_prompt
        )
        assert documented, f"batch prompt omits callable {name!r}"
    for key in definition.tool_keys:
        assert f"`{key.replace('.', '_')}`" in definition.system_prompt
        assert f"(`{key}`)" in definition.system_prompt
    assert "member grants, not direct tools of this coordinator" in definition.system_prompt
    assert "No web/network capability is granted." in definition.system_prompt
    assert "never claim a test/build/lint passed without an observed successful\nrun" in definition.system_prompt
    assert "Do not\nrepeat the call with a paraphrased task after success." in definition.system_prompt
