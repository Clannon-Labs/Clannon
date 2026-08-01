"""Narrow user-directed memory control for central orchestration.

The model never receives a general memory handle. It gets one command that can
delete only an inferred-memory id already selected by Manager for this turn.
Manager still owns tenant authorization and storage; this layer adds a second
least-privilege check so a guessed id never reaches the delete door.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

import settings
from core.llm import RunContext
from foundation import MemoryStore, ToolCallRecord


_DELETABLE_STORES = frozenset({
    MemoryStore.EPISODIC,
    MemoryStore.SEMANTIC,
    MemoryStore.PROCEDURAL,
})


def _record(ctx: object, memory_id: str, *, deleted: bool, error: str | None = None) -> None:
    """Keep the action visible to filter grounding and durable tool audit."""
    ctx.tool_calls.append(
        ToolCallRecord(
            tool_name="forget_memory",
            arguments={"memory_id": memory_id},
            result={"deleted": deleted} if deleted else None,
            success=deleted,
            duration_ms=0.0,
            error=error,
        )
    )


def build_forget_memory_tool() -> Callable:
    """Build the central-only native deletion command."""

    async def forget_memory(ctx: RunContext[Any], memory_id: str) -> dict[str, object]:
        """Delete one relevant learned-memory entry by its supplied memory id.

        Use only when user explicitly asks to forget/delete memory. The id must
        appear beside that item in RELEVANT USER CONTEXT. Never guess an id and
        never claim success unless returned ``deleted`` is true. User-authored
        wiki entries are managed from Memory page, not through this command.
        """
        started = time.monotonic()
        real_ctx = ctx.deps.ctx
        visible_ids = {
            str(getattr(item, "memory_id", "") or "")
            for item in (getattr(real_ctx, "hydration_items", None) or [])
            if (
                getattr(item, "memory_id", "")
                and getattr(item, "store", None) in _DELETABLE_STORES
            )
        }
        if not memory_id or memory_id not in visible_ids:
            reason = "memory id was not present in this turn's relevant context"
            _record(real_ctx, memory_id, deleted=False, error=reason)
            return {
                "deleted": False,
                "error": reason,
                "instruction": "Do not tell user memory was removed.",
            }

        memory = ctx.deps.memory
        if memory is None or not getattr(real_ctx, "user_id", ""):
            reason = "memory deletion is unavailable in this environment"
            _record(real_ctx, memory_id, deleted=False, error=reason)
            return {
                "deleted": False,
                "error": reason,
                "instruction": "Do not tell user memory was removed.",
            }

        try:
            deleted = await asyncio.wait_for(
                memory.delete_entry(real_ctx.user_id, memory_id),
                timeout=settings.MEMORY.write_timeout_s,
            )
        except Exception as exc:  # fail closed; user must never receive fabricated success
            reason = f"memory deletion failed: {type(exc).__name__}"
            _record(real_ctx, memory_id, deleted=False, error=reason)
            return {
                "deleted": False,
                "error": reason,
                "instruction": "Do not tell user memory was removed.",
            }

        if not deleted:
            reason = "memory was missing, foreign, or storage refused deletion"
            _record(real_ctx, memory_id, deleted=False, error=reason)
            return {
                "deleted": False,
                "error": reason,
                "instruction": "Do not tell user memory was removed.",
            }

        # Keep later reasoning/filter grounding from treating deleted content as
        # still-current prepared context during this same turn.
        real_ctx.hydration_items = [
            item
            for item in (getattr(real_ctx, "hydration_items", None) or [])
            if getattr(item, "memory_id", "") != memory_id
        ]
        record = ToolCallRecord(
            tool_name="forget_memory",
            arguments={"memory_id": memory_id},
            result={"deleted": True},
            success=True,
            duration_ms=round((time.monotonic() - started) * 1000, 2),
        )
        real_ctx.tool_calls.append(record)
        return {"deleted": True, "message": "Memory removed."}

    return forget_memory
