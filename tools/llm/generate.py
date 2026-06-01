"""LLM generation primitive.

The primitive defines the local contract for brokered model generation while
failing closed until model budgets, provider policy, and prompt boundaries are
connected to the capability broker.
"""

from __future__ import annotations

from typing import Any, Dict

from registry import tool
from tools.schemas.output import STANDARD_OUTPUT_SCHEMA


@tool(enabled=True, domain="llm", tags=["primitive", "generation"])
class LlmGenerateTool:
    """Represent a brokered LLM generation request."""

    name = "generate"
    description = (
        "Request model-backed text generation. This primitive fails closed until "
        "LLM policy and provider routing are implemented."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Prompt text to send to the model.",
            },
            "purpose": {
                "type": "string",
                "description": "Why model generation is needed.",
            },
            "max_output_chars": {
                "type": "integer",
                "description": "Maximum generated characters requested.",
                "default": 2000,
            },
        },
        "required": ["prompt", "purpose"],
    }
    output_schema = STANDARD_OUTPUT_SCHEMA

    def call(self, tool_input: dict) -> Dict[str, Any]:
        """Validate generation input and fail closed until policy exists."""
        prompt = str(tool_input.get("prompt", "")).strip()
        purpose = str(tool_input.get("purpose", "")).strip()

        if not prompt:
            return _fail("prompt is required")
        if not purpose:
            return _fail("purpose is required")

        return _fail(
            "llm generation is not enabled yet; model policy and provider "
            "routing must be connected first"
        )


def _fail(message: str) -> Dict[str, Any]:
    """Return the standard failure envelope for this primitive."""
    return {"success": False, "data": None, "error": message}
