"""Sandboxed shell execution primitive.

The shell surface is intentionally present but not executable yet. A safe shell
primitive needs command policy, sandbox isolation, timeout handling, and output
caps before it can run host commands. Until then this tool validates input and
fails closed.
"""

from __future__ import annotations

from typing import Any, Dict

from registry import tool
from tools.schemas.output import RICH_OUTPUT_SCHEMA


@tool(enabled=True, domain="shell", tags=["primitive", "sandbox"])
class ShellRunTool:
    """Represent a brokered shell command request."""

    name = "run"
    description = (
        "Request sandboxed command execution. This primitive fails closed until "
        "shell policy and sandboxing are implemented."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Command line to execute in a sandbox.",
            },
            "cwd": {
                "type": "string",
                "description": "Workspace-relative working directory.",
                "default": ".",
            },
            "timeout_ms": {
                "type": "integer",
                "description": "Requested execution timeout in milliseconds.",
                "default": 10000,
            },
        },
        "required": ["command"],
    }
    output_schema = RICH_OUTPUT_SCHEMA

    def call(self, tool_input: dict) -> Dict[str, Any]:
        """Validate command input and fail closed until sandbox policy exists."""
        command = str(tool_input.get("command", "")).strip()
        if not command:
            return _fail("command is required")

        return {
            "success": False,
            "data": {"stdout": "", "stderr": "", "exit_code": 126},
            "error": (
                "shell execution is not enabled yet; command policy and "
                "sandboxing must be implemented first"
            ),
        }


def _fail(message: str) -> Dict[str, Any]:
    """Return the rich failure envelope for this primitive."""
    return {
        "success": False,
        "data": {"stdout": "", "stderr": "", "exit_code": 2},
        "error": message,
    }
