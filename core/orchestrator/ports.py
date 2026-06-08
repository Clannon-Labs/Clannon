"""
Orchestrator-internal port protocols + the Ports bundle.

These contracts are used only inside the orchestrator (the loop dispatches
through them; wiring assembles concrete impls), so they live here rather than in
foundation. The cross-layer MemoryPort lives in foundation.ports — the
orchestrator consumes it but does not own it.

Swapping any seam (real experts, sandboxed tools, a different decision-log
transport) means providing a new class that satisfies the matching protocol and
wiring it in build_default_ports — the loop never changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from foundation import MemoryPort, ToolCallRecord, VrakshaContext

from .schemas import DecisionLogEntry, ExpertRequest, ExpertSummary, ToolRequest


@runtime_checkable
class DecisionLogSink(Protocol):
    """Where the loop streams decision-log entries; a richer transport can drop in."""

    async def emit(self, entry: DecisionLogEntry) -> None: ...


@runtime_checkable
class ExpertHandlerPort(Protocol):
    """
    Runs experts under least-privilege. Returns ONLY brief summaries to the
    orchestrator and writes full findings to ctx.expert_findings.
    """

    async def run_experts(
        self, requests: list[ExpertRequest], ctx: VrakshaContext
    ) -> list[ExpertSummary]: ...


@runtime_checkable
class ToolHandlerPort(Protocol):
    """Runs one tool under permission + timeout + output limits; records the call."""

    async def call_tool(self, request: ToolRequest, ctx: VrakshaContext) -> ToolCallRecord: ...


@dataclass
class Ports:
    """The seams the orchestrator loop depends on. Assembled by build_default_ports."""
    memory: MemoryPort
    experts: ExpertHandlerPort
    tools: ToolHandlerPort
    log: DecisionLogSink
