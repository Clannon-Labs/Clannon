"""
Cross-layer port protocols.

A port is the contract two layers agree on so neither has to import the other.
These live in foundation (the nearest common point) precisely so the consumer
and the implementer stay decoupled — each depends on the protocol, not on the
other layer's module.

Today this holds only MemoryPort (orchestrator <-> memory). Add more cross-layer
ports here as they appear; layer-internal ports stay inside their own layer.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .contracts import HydrationPackage, HydrationRequest, MemoryWriteProposal


@runtime_checkable
class MemoryPort(Protocol):
    """
    The ONLY way anything talks to the memory layer.

    The memory manager is the sole implementer; the orchestrator is the sole
    caller (for now). Memory internals (stores, policies, the future background
    memory-agent with its own LLM call) stay behind this door — callers see only
    these two methods.
    """

    async def hydrate(self, request: HydrationRequest) -> HydrationPackage:
        """Return ranked, budget-bounded context to inject before planning."""
        ...

    async def record_write_proposals(self, proposals: list[MemoryWriteProposal]) -> None:
        """Hand proposed writes to the manager; it decides whether/where to persist."""
        ...
