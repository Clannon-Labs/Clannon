"""The orchestrator is the memory broker (sole-broker, ARCHITECTURE.md §7.3):
`memory.search` stays natively offered to the orchestrator so it can broker
sub-task recall for stateless experts, and the baseline prompt tells it to."""

from pathlib import Path

from registry.capabilities import CapabilityKind, discover, registry


def _orchestrator_tool_keys():
    """The tool keys the gateway offers the orchestrator natively — every registered
    tool minus workspace-scoped ones (mirrors Capabilities.run_turn's selection)."""
    discover()
    specs = [registry.get_tool(c["key"]) for c in registry.cards(CapabilityKind.TOOL)]
    return {s.key for s in specs if s and not getattr(s.impl, "wants_workspace", False)}


def test_memory_search_is_offered_to_the_orchestrator():
    # the broker's own door: removing expert grants must never remove THIS
    assert "memory.search" in _orchestrator_tool_keys()


def test_baseline_prompt_instructs_the_orchestrator_to_broker():
    # the committed baseline (overlay may harden, never weaken — read the repo file)
    text = (Path(__file__).parent.parent / "prompts" / "orchestrator" / "system.md").read_text()
    assert "Brokering memory for experts" in text
    assert "memory.search" in text
