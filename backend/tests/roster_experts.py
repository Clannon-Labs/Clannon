"""The documentation + summarization experts, and the registry-derived expert list
the model-settings UI renders (so any expert added to the backend auto-surfaces)."""

from registry.capabilities import discover, registry


def test_documentation_and_summarization_register():
    # tool_grants + permission are pinned once, for every expert, in
    # tests/expert_contract.py::test_expert_registration_pins_least_privilege --
    # not duplicated here (Law 1). This test covers what that one doesn't: model_role.
    discover()
    docs = registry.get_expert("docs.writer")
    assert docs is not None and docs.model_role == "planner"

    summ = registry.get_expert("summary.condenser")
    assert summ is not None and summ.model_role == "research"

    assert {"docs.writer", "summary.condenser"} & {b.key for b in registry.broken()} == set()


def test_config_experts_auto_derives_from_registry():
    # config.EXPERTS is DERIVED from the registry, so a new backend expert shows up in
    # the model-settings UI with no edit to config.py.
    import api.config as cfg

    by_key = {e["key"]: e for e in cfg.EXPERTS}
    # the new experts are present alongside the originals
    assert {"web.research", "media.analyst", "docs.writer", "summary.condenser"} <= set(by_key)
    # every entry has the shape the UI + override logic expect, with a real role
    for e in cfg.EXPERTS:
        assert set(e) == {"key", "label", "role"} and e["role"]
    # role comes from the expert's model_role; label is derived from the key
    assert by_key["docs.writer"]["role"] == "planner"
    assert by_key["docs.writer"]["label"] == "Docs writer"
    assert by_key["media.analyst"]["role"] == "media_expert"
    # sorted by key, no broken experts leak in
    assert [e["key"] for e in cfg.EXPERTS] == sorted(by_key)
    assert all(e["key"] not in {b.key for b in registry.broken()} for e in cfg.EXPERTS)
