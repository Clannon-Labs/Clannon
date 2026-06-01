"""Read-only system inspection primitive.

This primitive returns bounded project/runtime metadata that is safe for the
agent to use when orienting itself. It does not inspect secrets, environment
variables, user home directories, or arbitrary host state.
"""

from __future__ import annotations

import platform
import sys
from typing import Any, Dict

from get_root import root
from registry import tool
from tools.schemas.output import STANDARD_OUTPUT_SCHEMA


@tool(enabled=True, domain="system", tags=["primitive", "read-only"])
class SystemInspectTool:
    """Return safe project and Python runtime metadata."""

    name = "inspect"
    description = "Return safe, read-only project and Python runtime metadata."
    input_schema = {
        "type": "object",
        "properties": {
            "include_python": {
                "type": "boolean",
                "description": "Include Python runtime metadata.",
                "default": True,
            }
        },
        "required": [],
    }
    output_schema = STANDARD_OUTPUT_SCHEMA

    def call(self, tool_input: dict) -> Dict[str, Any]:
        """Return a small metadata payload about the current project runtime."""
        include_python = bool(tool_input.get("include_python", True))
        data: dict[str, Any] = {
            "project_root": root.project.as_posix(),
            "cwd": root.project.as_posix(),
            "platform": platform.system().lower(),
        }

        if include_python:
            data["python"] = {
                "version": platform.python_version(),
                "executable_name": sys.executable.split("/")[-1],
                "implementation": platform.python_implementation(),
            }

        return {"success": True, "data": data, "error": None}
