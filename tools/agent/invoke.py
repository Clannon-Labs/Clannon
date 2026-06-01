"""Expert invocation primitive.

This primitive is a broker-facing placeholder for calling experts without
letting experts or tools invoke each other directly. It validates the intended
request shape now and fails closed until the orchestrator owns real expert
invocation routing, recursion limits, and audit semantics.
"""

from __future__ import annotations

from typing import Any, Dict

from registry import tool
from tools.schemas.output import STANDARD_OUTPUT_SCHEMA


@tool(enabled=True, domain="agent", tags=["primitive", "expert"])
class AgentInvokeTool:
    """Represent a brokered expert invocation request."""

    name = "invoke"
    description = (
        "Prepare an expert invocation request. This primitive fails closed until "
        "expert routing policy is implemented."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "expert": {
                "type": "string",
                "description": "Canonical expert key or domain/name to invoke.",
            },
            "payload": {
                "type": "object",
                "description": "Structured input intended for the expert.",
                "default": {},
            },
            "reason": {
                "type": "string",
                "description": "Reason this expert is needed.",
            },
        },
        "required": ["expert", "reason"],
    }
    output_schema = STANDARD_OUTPUT_SCHEMA

    def call(self, tool_input: dict) -> Dict[str, Any]:
        """Validate expert invocation input and fail closed by design."""
        expert = str(tool_input.get("expert", "")).strip()
        reason = str(tool_input.get("reason", "")).strip()
        payload = tool_input.get("payload", {})

        if not expert:
            return _fail("expert is required")
        if not reason:
            return _fail("reason is required")
        if not isinstance(payload, dict):
            return _fail("payload must be an object")

        return _fail(
            "expert invocation is not enabled yet; route expert messages "
            "through the agent orchestrator policy first"
        )


def _fail(message: str) -> Dict[str, Any]:
    """Return the standard failure envelope for this primitive."""
    return {"success": False, "data": None, "error": message}
