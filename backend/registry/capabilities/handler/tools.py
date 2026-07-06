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

import settings
from foundation import PermissionLevel, ToolCallRecord, VrakshaContext
from security.sanitizers.workers.text import scan as scan_text

from .. import CapabilityKind, registry as default_registry
from ..schemas import ToolRequest

_ALL_PERMISSIONS = frozenset(PermissionLevel)


class MemorySearcher:
    """Injected into a `wants_memory` tool: a narrow, READ-ONLY, user-scoped door into
    the memory layer. The tool never imports memory — it gets this and calls `search`.
    Reaches the MemoryPort (`core.memory.manager`) lazily from the handler layer (which
    already connects to core), so the tools/ package keeps importing only registry +
    foundation, and experts still never WRITE memory (CLAUDE.md constraint #4)."""

    def __init__(self, ctx: VrakshaContext) -> None:
        self._ctx = ctx

    async def search(self, query: str):
        """Ranked, user-scoped recall across the memory tiers + the user's wiki, via the
        MemoryPort's hydrate. Returns a HydrationPackage (items + a `degraded` flag when
        memory is temporarily unavailable). Best-effort: never raises into the tool."""
        from core.memory import manager  # the MemoryPort singleton (lazy; no import cycle)
        from foundation import HydrationPackage, HydrationRequest, NormalizedInput

        try:
            query_input = NormalizedInput(modality="text", content_type="text/plain", content=query)
            return await manager.hydrate(HydrationRequest.for_turn(self._ctx, query_input))
        except Exception:  # noqa: BLE001 — a memory fault degrades recall, never the run
            return HydrationPackage(degraded=True, notes="memory temporarily unavailable")


class ToolHandler:
    """Implements ToolHandlerPort over the capability registry."""

    def __init__(self, registry=default_registry, grants=_ALL_PERMISSIONS, allowed_keys=None, workspace=None) -> None:
        self._registry = registry
        self._grants = frozenset(grants)
        self._allowed_keys = None if allowed_keys is None else frozenset(allowed_keys)
        self._workspace = workspace   # per-run WorkspacePort for `wants_workspace` tools; None outside a workspace scope

    def scoped(self, allowed_keys, grants, workspace=None) -> "ToolHandler":
        """A handler restricted to specific tool keys + permission grants (for experts),
        optionally bound to a per-run workspace that its `wants_workspace` tools use.

        COMPOSES with this handler's own restriction — never widens it. `scoped()`
        can only narrow further, so nesting (an already-scoped batch orchestrator's
        expert calling `.scoped()` again via `_toolbox_for`) can't silently escape
        the outer scope. Without this intersection, a fresh `ToolHandler` built from
        `self._registry` with just the new args would ignore whatever restriction
        `self` already had — inert while `Capabilities.open()` was the only
        construction site (always unrestricted, so narrowing from "everything" was
        a no-op), but a real gap the moment a scoped `Capabilities` exists."""
        narrowed_keys = (
            allowed_keys if self._allowed_keys is None
            else self._allowed_keys if allowed_keys is None
            else self._allowed_keys & frozenset(allowed_keys)
        )
        narrowed_grants = frozenset(grants) & self._grants
        return ToolHandler(self._registry, grants=narrowed_grants, allowed_keys=narrowed_keys, workspace=workspace)

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

        impl = spec.impl()
        if getattr(impl, "wants_workspace", False):
            if self._workspace is None:
                return self._fail(request, ctx, started, "tool needs a workspace; not available in this scope")
            coro = impl.run(args, self._workspace)
        elif getattr(impl, "wants_memory", False):
            # read-only, user-scoped recall — built from this call's ctx (user_id, wiki)
            coro = impl.run(args, MemorySearcher(ctx))
        else:
            coro = impl.run(args)

        try:
            timeout = getattr(spec, "timeout_s", None) or settings.TOOLS.timeout_s
            output = await asyncio.wait_for(coro, timeout=timeout)
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
        """Invariant A: external text re-enters sanitization before reasoning.

        Recurses into nested list/dict/tuple so NO string leaf reaches the model
        unscanned — a top-level-only pass let structured NETWORK-tool output (e.g. a
        list of strings, or a nested object) bypass the sanitizer entirely."""
        return await self._sanitize_value(result)

    async def _sanitize_value(self, value):
        if isinstance(value, str):
            if not value:
                return value
            scanned = await scan_text(value)
            return (
                "[redacted: external content failed sanitization]"
                if not scanned.passed
                else (scanned.sanitized_text or value)
            )
        if isinstance(value, dict):
            return {k: await self._sanitize_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [await self._sanitize_value(v) for v in value]
        return value  # int/float/bool/None — nothing to scan

    def _cap(self, result: dict) -> dict:
        blob = json.dumps(result, default=str)
        if len(blob.encode("utf-8")) <= settings.TOOLS.max_output_bytes:
            return result
        return {"truncated": True, "preview": blob[:settings.TOOLS.tool_output_preview_chars]}
