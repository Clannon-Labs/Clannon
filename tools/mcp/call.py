"""MCP edge primitive.

This primitive exposes a stable local contract for future MCP calls while
delegating the actual edge behavior to the existing MCP adapter placeholder.
It remains fail-closed until a server transport is configured.
"""

from __future__ import annotations

from typing import Any, Dict

from registry import tool
from src.capabilities.contracts import Actor, CapabilityRequest
from tools.mcp.adapter import McpAdapter
from tools.schemas.output import STANDARD_OUTPUT_SCHEMA


@tool(enabled=True, domain="mcp", tags=["primitive", "external"])
class McpCallTool:
    """Call an external MCP capability through the adapter boundary."""

    name = "call"
    description = (
        "Request an external MCP capability. This primitive fails closed until "
        "an MCP server transport is configured."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "capability": {
                "type": "string",
                "description": "External MCP capability name.",
            },
            "arguments": {
                "type": "object",
                "description": "Arguments for the external MCP capability.",
                "default": {},
            },
            "reason": {
                "type": "string",
                "description": "Reason this external capability is needed.",
            },
        },
        "required": ["capability", "reason"],
    }
    output_schema = STANDARD_OUTPUT_SCHEMA

    def call(self, tool_input: dict) -> Dict[str, Any]:
        """Validate MCP call input and return the adapter's fail-closed result."""
        capability = str(tool_input.get("capability", "")).strip()
        reason = str(tool_input.get("reason", "")).strip()
        arguments = tool_input.get("arguments", {})

        if not capability:
            return _fail("capability is required")
        if not reason:
            return _fail("reason is required")
        if not isinstance(arguments, dict):
            return _fail("arguments must be an object")

        request = CapabilityRequest(
            capability=capability,
            arguments=arguments,
            reason=reason,
            caller=Actor(kind="tool", name="tool.mcp.call"),
        )
        return McpAdapter().call(request).to_tool_output()


def _fail(message: str) -> Dict[str, Any]:
    """Return the standard failure envelope for this primitive."""
    return {"success": False, "data": None, "error": message}
