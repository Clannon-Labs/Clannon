from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Any

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:  # pragma: no cover - depends on optional environment state
    ClientSession = None
    StdioServerParameters = None
    stdio_client = None
    MCP_AVAILABLE = False
else:
    MCP_AVAILABLE = True


def mcp_version() -> str | None:
    try:
        return version("mcp")
    except PackageNotFoundError:
        return None


@dataclass(slots=True, frozen=True)
class McpSdkStatus:
    available: bool
    version: str | None
    client_session: Any
    stdio_server_parameters: Any
    stdio_client: Any


def get_mcp_sdk_status() -> McpSdkStatus:
    return McpSdkStatus(
        available=MCP_AVAILABLE,
        version=mcp_version(),
        client_session=ClientSession,
        stdio_server_parameters=StdioServerParameters,
        stdio_client=stdio_client,
    )
