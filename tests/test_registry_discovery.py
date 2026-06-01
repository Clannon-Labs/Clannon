from registry.discovery import discover_registry_modules
from registry.register import Registry


def _restore_registry(previous_registry):
    """Restore the process-global registry after tests that import temp modules."""
    Registry._registry.clear()
    Registry._registry.update(previous_registry)


def test_discovery_registers_enabled_decorators_and_skips_disabled(tmp_path, monkeypatch):
    """Discovery imports enabled decorators and leaves disabled drafts unregistered."""
    package = tmp_path / "plugin_pack"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "enabled_tool.py").write_text(
        """
from registry.register import tool

@tool(enabled=True, domain="demo", tags=["ok"])
class EnabledTool:
    name = "enabled_tool"
    description = "Enabled test tool."
    input_schema = {"type": "object", "properties": {}, "required": []}
    output_schema = {"type": "object", "properties": {}}

    def call(self, tool_input):
        return {"success": True}
""",
        encoding="utf-8",
    )
    (package / "disabled_tool.py").write_text(
        """
from registry.register import tool

@tool(enabled=False, domain="demo", tags=["off"])
class DisabledTool:
    name = "disabled_tool"
    description = "Disabled test tool."
    input_schema = {"type": "object", "properties": {}, "required": []}
    output_schema = {"type": "object", "properties": {}}

    def call(self, tool_input):
        return {"success": True}
""",
        encoding="utf-8",
    )

    previous_registry = Registry._registry.copy()
    Registry._registry.clear()
    monkeypatch.syspath_prepend(str(tmp_path))

    try:
        errors = discover_registry_modules(tmp_path)

        assert errors == []
        assert "tool.demo.enabled_tool" in Registry.all()
        assert "tool.demo.disabled_tool" not in Registry.all()
    finally:
        _restore_registry(previous_registry)


def test_basic_tool_registration_supplies_standard_output_schema(tmp_path, monkeypatch):
    """A basic tool can use the public registry import and omit output schema."""
    package = tmp_path / "minimal_tool_pack"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "minimal_tool.py").write_text(
        '''
from registry import tool

@tool(domain="demo", tags=["minimal"])
class MinimalTool:
    name = "minimal_tool"
    description = "Small demo tool."
    input_schema = {"type": "object", "properties": {}, "required": []}

    def call(self, tool_input):
        return {"success": True, "data": {"seen": tool_input}, "error": None}
''',
        encoding="utf-8",
    )

    previous_registry = Registry._registry.copy()
    Registry._registry.clear()
    monkeypatch.syspath_prepend(str(tmp_path))

    try:
        errors = discover_registry_modules(tmp_path)
        entry = Registry.get("tool.demo.minimal_tool")

        assert errors == []
        assert entry is not None
        assert entry.cls.name == "minimal_tool"
        assert entry.cls.description == "Small demo tool."
        assert entry.cls.input_schema == {"type": "object", "properties": {}, "required": []}
        assert entry.cls.output_schema["properties"]["success"] == {"type": "boolean"}
    finally:
        _restore_registry(previous_registry)


def test_discovery_accepts_public_registry_expert_import(tmp_path, monkeypatch):
    """Discovery supports `from registry import expert` for author-facing code."""
    package = tmp_path / "public_expert_pack"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "SKILL.md").write_text(
        "# Public Expert\n\nUse this expert for public import tests.\n",
        encoding="utf-8",
    )
    (package / "public_expert.py").write_text(
        '''
from registry import expert

@expert(domain="demo")
class PublicExpert:
    name = "public_expert"
    description = "Reason about the public registry import."
    input_schema = {"type": "object", "properties": {}, "required": []}

    def call(self, tool_input):
        return {"success": True, "data": {}, "error": None}
''',
        encoding="utf-8",
    )

    previous_registry = Registry._registry.copy()
    Registry._registry.clear()
    monkeypatch.syspath_prepend(str(tmp_path))

    try:
        errors = discover_registry_modules(tmp_path)

        assert errors == []
        assert "expert.demo.public_expert" in Registry.all()
    finally:
        _restore_registry(previous_registry)


def test_primitive_tool_registration_requires_explicit_output_schema(tmp_path, monkeypatch):
    """Primitive tools must not rely on the basic-tool output-schema default."""
    package = tmp_path / "primitive_tool_pack"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "primitive_tool.py").write_text(
        '''
from registry.register import tool

@tool(domain="demo", tags=["primitive"])
class PrimitiveTool:
    name = "primitive_tool"
    description = "Primitive demo tool."
    input_schema = {"type": "object", "properties": {}, "required": []}

    def call(self, tool_input):
        return {"success": True, "data": {}, "error": None}
''',
        encoding="utf-8",
    )

    previous_registry = Registry._registry.copy()
    Registry._registry.clear()
    monkeypatch.syspath_prepend(str(tmp_path))

    try:
        errors = discover_registry_modules(tmp_path)

        assert "tool.demo.primitive_tool" not in Registry.all()
        assert len(errors) == 1
        assert "missing required field: 'output_schema'" in str(errors[0][1])
    finally:
        _restore_registry(previous_registry)


def test_expert_registration_infers_sibling_skill_file(tmp_path, monkeypatch):
    """A new expert can rely on a colocated SKILL.md and default output schema."""
    package = tmp_path / "minimal_expert_pack"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "SKILL.md").write_text(
        "# Minimal Expert\n\nUse this expert for registry tests.\n",
        encoding="utf-8",
    )
    (package / "minimal_expert.py").write_text(
        '''
from registry.register import expert

@expert(domain="demo")
class MinimalExpert:
    name = "minimal_expert"
    description = "Reason about a tiny demo task."
    input_schema = {"type": "object", "properties": {}, "required": []}

    def call(self, tool_input):
        return {"success": True, "data": {"ok": True}, "error": None}
''',
        encoding="utf-8",
    )

    previous_registry = Registry._registry.copy()
    Registry._registry.clear()
    monkeypatch.syspath_prepend(str(tmp_path))

    try:
        errors = discover_registry_modules(tmp_path)
        entry = Registry.get("expert.demo.minimal_expert")

        assert errors == []
        assert entry is not None
        assert entry.cls.name == "minimal_expert"
        assert entry.cls.description == "Reason about a tiny demo task."
        assert entry.cls.instruction_files == [
            (package / "SKILL.md").resolve().as_posix()
        ]
        assert entry.cls.output_schema["required"] == ["success"]
    finally:
        _restore_registry(previous_registry)
