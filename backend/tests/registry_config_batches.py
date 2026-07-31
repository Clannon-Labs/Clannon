"""
tests for registry/config/batches.py -- the batches.yaml loader. Mirrors the
fail-closed posture models.py's own loader has (same ConfigError shape), plus
the D7/D8-consistent grant ceiling: config may tighten a defense, never
silently loosen one -- NETWORK/ELEVATED can't be handed to a batch via YAML
alone (backend's security-review hardening, 2026-07-25).

Run:
    cd backend && .venv/bin/python -m pytest tests/registry_config_batches.py -v
"""

import pytest

from foundation import ConfigError
from registry.config.batches import _load_batches
from registry.config.prompts import PromptRegistry


def _write(tmp_path, text: str):
    path = tmp_path / "batches.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_file_fails_closed(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        _load_batches(tmp_path / "does-not-exist.yaml")


def test_malformed_yaml_fails_closed(tmp_path):
    path = _write(tmp_path, "engineering: [unclosed")
    with pytest.raises(ConfigError, match="not valid YAML"):
        _load_batches(path)


def test_non_mapping_top_level_fails_closed(tmp_path):
    path = _write(tmp_path, "- just\n- a\n- list\n")
    with pytest.raises(ConfigError, match="must be a mapping"):
        _load_batches(path)


def test_non_mapping_entry_fails_closed(tmp_path):
    path = _write(tmp_path, "engineering: not-a-mapping\n")
    with pytest.raises(ConfigError, match="must be a mapping"):
        _load_batches(path)


def test_missing_domain_field_fails_closed(tmp_path):
    path = _write(tmp_path, """
engineering:
  expert_keys: [code.engineer]
  tool_keys: [fs.read]
  grants: [read]
""")
    with pytest.raises(ConfigError, match="missing required field"):
        _load_batches(path)


def test_bad_grant_value_fails_closed(tmp_path):
    path = _write(tmp_path, """
engineering:
  domain: engineering
  expert_keys: [code.engineer]
  tool_keys: [fs.read]
  grants: [not-a-real-permission]
""")
    with pytest.raises(ConfigError, match="invalid grant"):
        _load_batches(path)


@pytest.mark.parametrize("grant", ["network", "elevated"])
def test_network_and_elevated_grants_are_rejected(tmp_path, grant):
    """The ceiling: a batches.yaml edit alone must never be able to hand a
    batch egress or elevated access, even though PermissionLevel(grant) is a
    perfectly valid enum value -- this is a policy rejection, not a parse
    error, so it must fire AFTER the grant parses cleanly."""
    path = _write(tmp_path, f"""
engineering:
  domain: engineering
  expert_keys: [code.engineer]
  tool_keys: [fs.read]
  grants: [{grant}]
""")
    with pytest.raises(ConfigError, match="forbidden grant"):
        _load_batches(path)


def test_read_write_execute_grants_are_accepted(tmp_path):
    path = _write(tmp_path, """
engineering:
  domain: engineering
  expert_keys: [code.engineer]
  tool_keys: [fs.read, fs.write, code.run]
  grants: [read, write, execute]
""")
    batches = _load_batches(path)
    assert set(batches) == {"engineering"}
    definition = batches["engineering"]
    assert definition.domain == "engineering"
    assert definition.expert_keys == frozenset({"code.engineer"})


def test_loader_injects_overlay_resolved_registry_prompt(tmp_path):
    base = tmp_path / "prompts"
    overlay = tmp_path / "prompts.secure"
    (base / "batches" / "engineering" / "orchestrator").mkdir(parents=True)
    (overlay / "batches" / "engineering" / "orchestrator").mkdir(parents=True)
    (base / "registry.yaml").write_text(
        "batch_orchestrator.engineering:\n"
        "  version: 1\n"
        "  file: batches/engineering/orchestrator/system.md\n"
        "  locked: false\n",
        encoding="utf-8",
    )
    (base / "batches" / "engineering" / "orchestrator" / "system.md").write_text(
        "BASE BATCH", encoding="utf-8"
    )
    (overlay / "batches" / "engineering" / "orchestrator" / "system.md").write_text(
        "OVERLAY BATCH", encoding="utf-8"
    )
    prompts = PromptRegistry.from_dir(base, overlay_dir=overlay)
    path = _write(tmp_path, """
engineering:
  domain: engineering
  expert_keys: [code.engineer]
  tool_keys: [fs.read]
  grants: [read]
""")

    definition = _load_batches(path, prompt_registry=prompts)["engineering"]

    assert definition.system_prompt == "OVERLAY BATCH"


def test_batch_with_no_matching_prompt_entry_fails_closed(tmp_path):
    """Per-batch prompts, not a shared default: a batch_key with no
    `batch_orchestrator.<batch_key>` entry in the prompt registry must never
    silently fall back to some other batch's (or a shared) prompt."""
    base = tmp_path / "prompts"
    (base / "batches" / "engineering" / "orchestrator").mkdir(parents=True)
    (base / "registry.yaml").write_text(
        "batch_orchestrator.engineering:\n"
        "  version: 1\n"
        "  file: batches/engineering/orchestrator/system.md\n"
        "  locked: false\n",
        encoding="utf-8",
    )
    (base / "batches" / "engineering" / "orchestrator" / "system.md").write_text(
        "ENGINEERING PROMPT", encoding="utf-8"
    )
    prompts = PromptRegistry.from_dir(base)
    path = _write(tmp_path, """
engineering:
  domain: engineering
  expert_keys: [code.engineer]
  tool_keys: [fs.read]
  grants: [read]
research:
  domain: research
  expert_keys: [code.engineer]
  tool_keys: [fs.read]
  grants: [read]
""")

    with pytest.raises(ConfigError, match="no registered prompt 'batch_orchestrator.research'"):
        _load_batches(path, prompt_registry=prompts)


def test_two_batches_with_different_prompts_get_different_prompt_text(tmp_path):
    """The whole point of per-batch prompts: two batches never share text, even
    when both are perfectly valid and both resolve cleanly."""
    base = tmp_path / "prompts"
    (base / "batches" / "engineering" / "orchestrator").mkdir(parents=True)
    (base / "batches" / "research" / "orchestrator").mkdir(parents=True)
    (base / "registry.yaml").write_text(
        "batch_orchestrator.engineering:\n"
        "  version: 1\n"
        "  file: batches/engineering/orchestrator/system.md\n"
        "  locked: false\n"
        "batch_orchestrator.research:\n"
        "  version: 1\n"
        "  file: batches/research/orchestrator/system.md\n"
        "  locked: false\n",
        encoding="utf-8",
    )
    (base / "batches" / "engineering" / "orchestrator" / "system.md").write_text(
        "ENGINEERING PROMPT", encoding="utf-8"
    )
    (base / "batches" / "research" / "orchestrator" / "system.md").write_text(
        "RESEARCH PROMPT", encoding="utf-8"
    )
    prompts = PromptRegistry.from_dir(base)
    path = _write(tmp_path, """
engineering:
  domain: engineering
  expert_keys: [code.engineer]
  tool_keys: [fs.read]
  grants: [read]
research:
  domain: research
  expert_keys: [code.engineer]
  tool_keys: [fs.read]
  grants: [read]
""")

    batches = _load_batches(path, prompt_registry=prompts)

    assert batches["engineering"].system_prompt == "ENGINEERING PROMPT"
    assert batches["research"].system_prompt == "RESEARCH PROMPT"
    assert batches["engineering"].system_prompt != batches["research"].system_prompt


def test_empty_file_yields_no_batches(tmp_path):
    path = _write(tmp_path, "")
    assert _load_batches(path) == {}
