"""
Tool handler — the orchestrator's door to tools.

Phase 1 is a stub, but it already runs the permission-check SEAM and records the
call on ctx.tool_calls, so the least-privilege boundary and the audit trail are
real from the start.

TODO: a tool registry (name -> PermissionLevel + callable), least-privilege
enforcement against the caller's grants, and sandboxed execution
(restrictedpython / Docker) bounded by TOOL_TIMEOUT_S, TOOL_SANDBOX_TIMEOUT_S,
and TOOL_MAX_OUTPUT_BYTES.
"""

from __future__ import annotations

import time

from foundation import PermissionLevel, ToolCallRecord, VrakshaContext

from ..schemas import ToolRequest


class StubToolHandler:
    """Phase-1 ToolHandlerPort implementation."""

    def __init__(self, registry: dict[str, PermissionLevel] | None = None) -> None:
        # name -> required PermissionLevel. Empty for now; the real tool registry
        # populates this and the handler enforces it against the caller's grants.
        self._registry: dict[str, PermissionLevel] = registry or {}

    async def call_tool(self, request: ToolRequest, ctx: VrakshaContext) -> ToolCallRecord:
        started = time.monotonic()

        # Permission seam: a known tool would be permission-checked here before any
        # execution. Unknown tools simply have no grant yet. (Enforcement + sandbox
        # land with the real registry.)
        _required = self._registry.get(request.name)

        record = ToolCallRecord(
            tool_name=request.name,
            arguments=request.arguments,
            result=None,
            success=False,
            duration_ms=round((time.monotonic() - started) * 1000, 2),
            error="tool handler not implemented (stub)",
        )
        ctx.tool_calls.append(record)
        return record
