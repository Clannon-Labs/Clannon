"""
Characterization test: the ``@tool`` / ``@expert`` decorators in
``registry/capabilities/registration.py`` must keep mirroring every capability
class attribute onto the ``ToolSpec`` / ``ExpertSpec``. That mirror is a
hand-maintained parallel surface: a spec field and the decorator line that fills
it from the class are edited in two places, so they rot quietly when one side
changes without the other.

What this pins (observed by RUNNING the decorators, not by reading them):
  * the exact set of spec fields the decorator copies FROM a class attribute
    (the "mirrored" set), each verified with a sentinel value that must flow
    through;
  * the fields the decorator derives WITHOUT a class attribute (``kind``,
    ``impl``);
  * the lifecycle fields it leaves at their dataclass default for ``register()``
    to own (``status``, ``reason``).

Drift caught:
  * a new ``ToolSpec`` / ``ExpertSpec`` field added but not wired into the
    decorator -> the field-accounting assertion trips (the field is in no
    partition), forcing a conscious classify-or-wire decision;
  * a mirrored line dropped from the decorator -> the sentinel for that field no
    longer flows through;
  * the reverse (the decorator reads a class attr for a field the spec no longer
    has) is already fatal at construction time, e.g. ``ToolSpec(stale=...)``
    raises ``TypeError`` the moment discovery runs.

Assert CURRENT behavior only; this test does not change the decorator or the
specs. Observed mirror set on 2026-06-20: see the partitions below.
"""

import dataclasses

from pydantic import BaseModel

from foundation import PermissionLevel
from registry.capabilities import (
    CapabilityKind,
    ExpertSpec,
    ToolSpec,
)
from registry.capabilities import registration


class _In(BaseModel):
    x: str


class _Out(BaseModel):
    y: str


# --- field partitions, by spec field name (the present, observed mirror set) ---
#
# MIRRORED maps each spec field -> the class attribute the decorator reads it
# from. The attribute name equals the field name for every field EXCEPT the
# expert ``tool_grants``, which the decorator reads from the class ``tools``
# attribute.
_BASE_MIRRORED = {
    "name": "name",
    "description": "description",
    "domain": "domain",
    "tags": "tags",
    "permission": "permission",
    "input_schema": "input_schema",
    "output_schema": "output_schema",
    "eager": "eager",
}
_TOOL_MIRRORED = {**_BASE_MIRRORED, "timeout_s": "timeout_s"}
_EXPERT_MIRRORED = {
    **_BASE_MIRRORED,
    "model_role": "model_role",
    "tool_grants": "tools",  # class attribute is `tools`; spec field is `tool_grants`
    "skills": "skills",
}

# Set by the decorator without reading a class attribute.
_DERIVED = {"kind", "impl"}
# Left at the dataclass default by the decorator; register() fills these.
_LIFECYCLE = {"status", "reason"}

# A distinct, non-default value per class attribute, so a dropped mirror line
# surfaces as the field falling back to its default instead of the sentinel.
# Every value below differs from the corresponding dataclass default.
_SENTINELS = {
    "name": "drift_name",
    "description": "drift_description",
    "domain": "drift_domain",
    "tags": ("alpha", "beta"),          # default ()
    "permission": PermissionLevel.WRITE,  # default READ
    "input_schema": _In,
    "output_schema": _Out,
    "eager": True,                        # default False
    "timeout_s": 12.5,                    # default None
    "model_role": "synthesis",            # default "research"
    "tools": ("drift_domain.some_tool",),  # -> tool_grants, default ()
    "skills": ("skill.md",),             # default ()
}


def _make_impl(class_attrs):
    """A minimal capability class carrying the given sentinel class attributes."""
    async def run(self, *args):  # validate() only checks this is a coroutine fn
        return _Out(y="ok")

    namespace = {attr: _SENTINELS[attr] for attr in class_attrs}
    namespace["run"] = run
    return type("DriftStub", (), namespace)


def _capture_spec(decorator, impl, monkeypatch):
    """Run a decorator and return the spec it builds, without touching the
    process-wide registry (we intercept register() so nothing is stored)."""
    captured = {}

    def fake_register(spec, reason=None):
        captured["spec"] = spec
        captured["reason"] = reason
        return spec

    monkeypatch.setattr(registration.registry, "register", fake_register)
    decorator(impl)
    return captured["spec"]


# --- @tool ---

def test_tool_decorator_mirrors_class_attributes(monkeypatch):
    impl = _make_impl(_TOOL_MIRRORED.values())
    spec = _capture_spec(registration.tool, impl, monkeypatch)
    for field, class_attr in _TOOL_MIRRORED.items():
        assert getattr(spec, field) == _SENTINELS[class_attr], (
            f"@tool no longer mirrors class.{class_attr} onto ToolSpec.{field}"
        )


def test_tool_spec_fields_fully_accounted():
    fields = {f.name for f in dataclasses.fields(ToolSpec)}
    accounted = set(_TOOL_MIRRORED) | _DERIVED | _LIFECYCLE
    assert fields == accounted, (
        "ToolSpec fields drifted from the @tool decorator's mirror set. "
        "Wire the new field in registry/capabilities/registration.py AND add it "
        "to the partition in this test (or classify it as derived/lifecycle). "
        f"unaccounted={fields - accounted} stale={accounted - fields}"
    )


def test_tool_derived_and_lifecycle_fields(monkeypatch):
    impl = _make_impl(_TOOL_MIRRORED.values())
    spec = _capture_spec(registration.tool, impl, monkeypatch)
    assert spec.kind is CapabilityKind.TOOL
    assert spec.impl is impl
    for name in _LIFECYCLE:
        assert getattr(spec, name) == ToolSpec.__dataclass_fields__[name].default


# --- @expert ---

def test_expert_decorator_mirrors_class_attributes(monkeypatch):
    impl = _make_impl(_EXPERT_MIRRORED.values())
    spec = _capture_spec(registration.expert, impl, monkeypatch)
    for field, class_attr in _EXPERT_MIRRORED.items():
        assert getattr(spec, field) == _SENTINELS[class_attr], (
            f"@expert no longer mirrors class.{class_attr} onto ExpertSpec.{field}"
        )


def test_expert_spec_fields_fully_accounted():
    fields = {f.name for f in dataclasses.fields(ExpertSpec)}
    accounted = set(_EXPERT_MIRRORED) | _DERIVED | _LIFECYCLE
    assert fields == accounted, (
        "ExpertSpec fields drifted from the @expert decorator's mirror set. "
        "Wire the new field in registry/capabilities/registration.py AND add it "
        "to the partition in this test (or classify it as derived/lifecycle). "
        f"unaccounted={fields - accounted} stale={accounted - fields}"
    )


def test_expert_derived_and_lifecycle_fields(monkeypatch):
    impl = _make_impl(_EXPERT_MIRRORED.values())
    spec = _capture_spec(registration.expert, impl, monkeypatch)
    assert spec.kind is CapabilityKind.EXPERT
    assert spec.impl is impl
    for name in _LIFECYCLE:
        assert getattr(spec, name) == ExpertSpec.__dataclass_fields__[name].default
