"""
Generic tool handler — registry-driven, zero per-tool wiring.

Looks a tool up by key, enforces the caller's grants + permission, validates args,
runs it under a timeout + output cap, and (invariant A) re-sanitizes the output of
NETWORK tools before it can reach reasoning. Every outcome is a structured
ToolCallRecord recorded on the context — unknown/broken/failed tools return
success=False with a reason, never silence.
"""

from __future__ import annotations

import asyncio
import json
import time

from foundation import PermissionLevel, ToolCallRecord, VrakshaContext, constants
from security.sanitizers.workers.text import scan as scan_text

from .. import CapabilityKind, registry as default_registry
from ..schemas import ToolRequest

_ALL_PERMISSIONS = frozenset(PermissionLevel)


class ToolHandler:
    """Implements ToolHandlerPort over the capability registry."""

    def __init__(self, registry=default_registry, grants=_ALL_PERMISSIONS, allowed_keys=None) -> None:
        self._registry = registry
        self._grants = frozenset(grants)
        self._allowed_keys = None if allowed_keys is None else frozenset(allowed_keys)

    def scoped(self, allowed_keys, grants) -> "ToolHandler":
        """A handler restricted to specific tool keys + permission grants (for experts)."""
        return ToolHandler(self._registry, grants=grants, allowed_keys=allowed_keys)

    async def call_tool(self, request: ToolRequest, ctx: VrakshaContext) -> ToolCallRecord:
        started = time.monotonic()

        spec = self._registry.get_tool(request.key)
        if spec is None:
            reason = self._registry.describe_missing(CapabilityKind.TOOL, request.key)
            return self._fail(request, ctx, started, reason)
        if self._allowed_keys is not None and spec.key not in self._allowed_keys:
            return self._fail(request, ctx, started, f"tool {spec.key!r} not granted to this caller")
        if spec.permission not in self._grants:
            return self._fail(request, ctx, started, f"permission denied: needs {spec.permission.value}")

        try:
            args = spec.input_schema(**request.arguments)
        except Exception as exc:
            return self._fail(request, ctx, started, f"bad arguments: {exc}")

        try:
            timeout = getattr(spec, "timeout_s", None) or constants.TOOL_TIMEOUT_S
            output = await asyncio.wait_for(spec.impl().run(args), timeout=timeout)
        except asyncio.TimeoutError:
            return self._fail(request, ctx, started, "tool timed out")
        except Exception as exc:
            return self._fail(request, ctx, started, f"tool error: {exc}")

        result = output.model_dump() if hasattr(output, "model_dump") else dict(output)
        if spec.permission == PermissionLevel.NETWORK:
            result = await self._sanitize(result)        # invariant A
        result = self._cap(result)

        record = ToolCallRecord(
            tool_name=spec.key,
            arguments=dict(request.arguments),
            result=result,
            success=True,
            duration_ms=round((time.monotonic() - started) * 1000, 2),
        )
        ctx.tool_calls.append(record)
        return record

    # --- helpers ---

    def _fail(self, request: ToolRequest, ctx: VrakshaContext, started: float, reason: str) -> ToolCallRecord:
        record = ToolCallRecord(
            tool_name=request.key,
            arguments=dict(request.arguments),
            result=None,
            success=False,
            duration_ms=round((time.monotonic() - started) * 1000, 2),
            error=reason,
        )
        ctx.tool_calls.append(record)
        return record

    async def _sanitize(self, result: dict) -> dict:
        """Invariant A: external text re-enters sanitization before reasoning."""
        cleaned: dict = {}
        for key, value in result.items():
            if isinstance(value, str) and value:
                scanned = await scan_text(value)
                cleaned[key] = (
                    "[redacted: external content failed sanitization]"
                    if not scanned.passed
                    else (scanned.sanitized_text or value)
                )
            else:
                cleaned[key] = value
        return cleaned

    def _cap(self, result: dict) -> dict:
        blob = json.dumps(result, default=str)
        if len(blob.encode("utf-8")) <= constants.TOOL_MAX_OUTPUT_BYTES:
            return result
        return {"truncated": True, "preview": blob[:1000]}
