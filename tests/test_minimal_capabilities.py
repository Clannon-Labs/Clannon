"""Smoke tests for the active primitive capability surface."""

from registry.discovery import discover_registry_modules
from registry.register import Registry

import pytest


def test_primitive_tools_and_smoke_expert_register_and_call():
    """The first primitive tools and smoke expert register with envelopes."""
    discover_registry_modules()

    filesystem_entry = Registry.get("tool.filesystem.operate")
    system_entry = Registry.get("tool.system.inspect")
    shell_entry = Registry.get("tool.shell.run")
    smoke_entry = Registry.get("expert.architecture.smoke_check")

    assert filesystem_entry is not None
    assert system_entry is not None
    assert shell_entry is not None
    assert smoke_entry is not None

    system_result = system_entry.cls().call({"include_python": False})
    assert system_result["success"] is True
    assert "project_root" in system_result["data"]

    assert shell_entry.cls().call({"command": "git status"}) == {
        "success": False,
        "data": {"stdout": "", "stderr": "", "exit_code": 126},
        "error": (
            "shell execution is not enabled yet; command policy and "
            "sandboxing must be implemented first"
        ),
    }

    assert smoke_entry.cls().call({"subject": "registry"}) == {
        "success": True,
        "data": {
            "subject": "registry",
            "diagnosis": "expert path reachable",
            "instruction_files": ["experts/architecture_smoke/SKILL.md"],
        },
        "error": None,
    }


@pytest.mark.anyio
async def test_minimal_capabilities_are_agent_visible():
    """The LLM sees the intended primitive capability names."""
    from src.agent.bootstrap import bootstrap_vraksha
    from src.agent.runtime import vraksha_agent
    from pydantic_ai.models.test import TestModel

    model = TestModel(call_tools=[], custom_output_text="ok")
    await vraksha_agent.run(
        "Check available capabilities.",
        deps=bootstrap_vraksha(),
        model=model,
    )

    tool_names = {
        tool.name for tool in model.last_model_request_parameters.function_tools
    }

    assert "expert_architecture_smoke_check" in tool_names
    assert "tool_agent_invoke" in tool_names
    assert "tool_filesystem_operate" in tool_names
    assert "tool_llm_generate" in tool_names
    assert "tool_mcp_call" in tool_names
    assert "tool_shell_run" in tool_names
    assert "tool_system_inspect" in tool_names
    assert "tool_web_fetch" in tool_names
    assert "tool_universal_echo" not in tool_names
    assert "tool_memory_search" not in tool_names
