"""Tests for the unified capability registry (specs, validation, store, discovery)."""

from pydantic import BaseModel

from registry.capabilities import (
    CapabilityKind,
    CapabilityRegistry,
    ExpertSpec,
    ToolSpec,
    discover,
    registry,
)
from registry.capabilities import validate


class _In(BaseModel):
    x: str


class _Out(BaseModel):
    y: str


def _tool_impl():
    class Impl:
        async def run(self, args):
            return _Out(y="ok")
    return Impl


def _tool_spec(name="t", domain="d", description="desc", impl=None):
    return ToolSpec(
        name=name, kind=CapabilityKind.TOOL, description=description, domain=domain,
        impl=impl or _tool_impl(), input_schema=_In, output_schema=_Out,
    )


# --- validation ---

def test_valid_tool_passes():
    assert validate(_tool_spec()) is None


def test_missing_domain_invalid():
    assert validate(_tool_spec(domain="")) == "missing domain"


def test_tool_requires_input_schema():
    spec = ToolSpec(name="t", kind=CapabilityKind.TOOL, description="d", domain="d",
                    impl=_tool_impl(), output_schema=_Out)
    assert "input_schema" in validate(spec)


def test_non_async_run_invalid():
    class Impl:
        def run(self, args):  # not async
            return _Out(y="x")
    spec = ToolSpec(name="t", kind=CapabilityKind.TOOL, description="d", domain="d",
                    impl=Impl, input_schema=_In, output_schema=_Out)
    assert "async run" in validate(spec)


def test_expert_requires_skill():
    class Impl:
        async def run(self, args, env):
            return _Out(y="x")
    spec = ExpertSpec(name="e", kind=CapabilityKind.EXPERT, description="d", domain="d",
                      impl=Impl, input_schema=_In, output_schema=_Out, skills=())
    assert "skill" in validate(spec)


def test_expert_requires_input_schema():
    class Impl:
        async def run(self, args, env):
            return _Out(y="x")
    spec = ExpertSpec(name="e", kind=CapabilityKind.EXPERT, description="d", domain="d",
                      impl=Impl, output_schema=_Out, skills=("s.md",))
    assert "input_schema" in validate(spec)


# --- store ---

def test_register_ok_and_catalog():
    reg = CapabilityRegistry()
    reg.register(_tool_spec(), None)
    assert [c["key"] for c in reg.catalog(CapabilityKind.TOOL)] == ["d.t"]
    assert reg.get_tool("d.t") is not None


def test_duplicate_key_marked_broken():
    reg = CapabilityRegistry()
    reg.register(_tool_spec(), None)
    reg.register(_tool_spec(description="dup"), None)
    assert len(reg.catalog(CapabilityKind.TOOL)) == 1
    assert reg.status(CapabilityKind.TOOL, "d.t")[0].value == "ok"
    assert len(reg.broken()) == 1


def test_invalid_marked_broken_and_excluded():
    reg = CapabilityRegistry()
    reg.register(_tool_spec(), "bad thing")
    assert reg.catalog(CapabilityKind.TOOL) == []
    status, reason = reg.status(CapabilityKind.TOOL, "d.t")
    assert status.value == "broken" and reason == "bad thing"


# --- discovery (global registry, idempotent) ---

def test_discover_populates_real_capabilities():
    discover()
    tools = {c["key"] for c in registry.catalog(CapabilityKind.TOOL)}
    experts = {c["key"] for c in registry.catalog(CapabilityKind.EXPERT)}
    assert {"search.web", "web.fetch_url", "code.python_exec", "math.calculator"} <= tools
    assert {"web.research", "synthesis.writer"} <= experts
