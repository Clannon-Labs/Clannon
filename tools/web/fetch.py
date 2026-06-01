"""Web fetch primitive.

The web surface is declared now but does not perform network access yet. It
validates the desired request shape and fails closed until network policy,
source allowlists, rate limits, and fetch implementation are connected.
"""

from __future__ import annotations

from typing import Any, Dict

from registry import tool
from tools.schemas.output import STANDARD_OUTPUT_SCHEMA


@tool(enabled=True, domain="web", tags=["primitive", "network"])
class WebFetchTool:
    """Represent a brokered web fetch request."""

    name = "fetch"
    description = (
        "Request a web page fetch. This primitive fails closed until network "
        "policy and fetch implementation are configured."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "HTTP or HTTPS URL to fetch.",
            },
            "max_bytes": {
                "type": "integer",
                "description": "Maximum response bytes requested.",
                "default": 100000,
            },
        },
        "required": ["url"],
    }
    output_schema = STANDARD_OUTPUT_SCHEMA

    def call(self, tool_input: dict) -> Dict[str, Any]:
        """Validate URL input and fail closed until web policy exists."""
        url = str(tool_input.get("url", "")).strip()
        if not url:
            return _fail("url is required")
        if not (url.startswith("http://") or url.startswith("https://")):
            return _fail("url must start with http:// or https://")

        return _fail(
            "web fetch is not enabled yet; network policy and source controls "
            "must be implemented first"
        )


def _fail(message: str) -> Dict[str, Any]:
    """Return the standard failure envelope for this primitive."""
    return {"success": False, "data": None, "error": message}
