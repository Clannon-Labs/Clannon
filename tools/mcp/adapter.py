from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.capabilities import CapabilityRequest, CapabilityResult
from tools.mcp.sdk import get_mcp_sdk_status


@dataclass(slots=True, frozen=True)
class McpServerConfig:
    name: str
    transport: str
    command: str | None = None
    url: str | None = None
    env: dict[str, str] = field(default_factory=dict)


class McpAdapter:
    """Placeholder boundary for future MCP-backed capabilities."""

    def __init__(self, servers: list[McpServerConfig] | None = None) -> None:
        self.servers = servers or []
        self.sdk = get_mcp_sdk_status()

    def call(self, request: CapabilityRequest) -> CapabilityResult:
        if not self.sdk.available:
            return CapabilityResult.fail(
                request,
                code="mcp_sdk_missing",
                message="MCP SDK is not installed. Install the `mcp` package.",
                retryable=False,
            )

        return CapabilityResult.fail(
            request,
            code="mcp_not_configured",
            message=(
                "MCP SDK is available, but this adapter is not wired to a "
                "server yet."
            ),
            retryable=False,
        )
