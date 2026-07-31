"""Memory Manager is sole broker; reasoning agents have no memory surface."""

from pathlib import Path

from registry.capabilities import CapabilityKind, discover, registry


def _orchestrator_tool_keys():
    """The tool keys the gateway offers the orchestrator natively — every registered
    tool minus workspace-scoped ones (mirrors Capabilities.run_turn's selection)."""
    discover()
    specs = [registry.get_tool(c["key"]) for c in registry.cards(CapabilityKind.TOOL)]
    return {s.key for s in specs if s and not getattr(s.impl, "wants_workspace", False)}


def test_no_memory_tool_is_offered_to_the_orchestrator():
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


def test_baseline_prompt_denies_memory_management():
    text = (Path(__file__).parent.parent / "prompts" / "orchestrator" / "system.md").read_text()
    assert "Do not manage, classify, store, search" in text
    assert "memory.search" not in text
    assert "remember(" not in text
