"""Static contract for central and batch orchestrator prompts.

These assertions are intentionally discriminating: routing must come from
explicit presentation intent, not from weak-model tool choice or answer shape.
"""

import re
from pathlib import Path

import yaml


BACKEND = Path(__file__).resolve().parents[1]
PROMPTS = BACKEND / "prompts"
OVERLAY = BACKEND / "prompts.secure"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_orchestrator_prompts_are_clannon_only_with_no_copied_provider_identity():
    central = _read(PROMPTS / "orchestrator" / "system.md")
    batch = _read(PROMPTS / "batches" / "engineering" / "orchestrator" / "system.md")
    assert "You are Clannon" in central
    assert "answer as Clannon" in central
    assert "one short sentence\n(25 words maximum)" in central
    assert "Do not explain features, architecture, tools, or workflow" in central
    assert "Do not append a generic “How can I help?” question." in central
    assert "Clannon batch orchestrator" in batch
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
    assert "internal, scoped Clannon batch orchestrator" in text
    assert "one delegated\nsub-task" in text
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


def test_registry_declares_central_v6_and_batch_v1_prompts():
    manifest = yaml.safe_load(_read(PROMPTS / "registry.yaml"))
    assert manifest["orchestrator"] == {
        "version": 6,
        "file": "orchestrator/system.md",
        "locked": False,
        "about": True,
    }
    assert manifest["batch_orchestrator.engineering"] == {
        "version": 1,
        "file": "batches/engineering/orchestrator/system.md",
        "locked": False,
    }


def test_active_local_overlays_match_committed_prompt_behavior_when_present():
    for relative in ("orchestrator/system.md", "batches/engineering/orchestrator/system.md"):
        baseline = PROMPTS / relative
        overlay = OVERLAY / relative
        if overlay.exists():
            assert _read(overlay) == _read(baseline)
