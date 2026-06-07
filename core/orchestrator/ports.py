"""
Orchestrator-internal port protocols + the Ports bundle.

These contracts are used only inside the orchestrator (the loop dispatches
through them; wiring assembles concrete impls), so they live here rather than in
foundation. The cross-layer MemoryPort lives in foundation.ports — the
orchestrator consumes it but does not own it.

Swapping any seam (real experts, sandboxed tools, entropy router, a different
decision-log transport) means providing a new class that satisfies the matching
protocol and wiring it in build_default_ports — the loop never changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from foundation import MemoryPort, NormalizedInput, ToolCallRecord, VrakshaContext

from .schemas import DecisionLogEntry, ExpertRequest, ExpertSummary, ToolRequest


@runtime_checkable
class DecisionLogSink(Protocol):
    """Where the loop streams decision-log entries. The UI drains the other end."""

    async def emit(self, entry: DecisionLogEntry) -> None: ...
    async def close(self) -> None: ...


@runtime_checkable
class ExpertRouter(Protocol):
    """
    Decides which experts (and how many) to run for a request. The default is a
    simple deterministic strategy; the entropy-over-embeddings router will satisfy
    this same protocol later.
    """

    def route(self, normalized: NormalizedInput, candidates: list[str]) -> list[ExpertRequest]: ...


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
    router: ExpertRouter
    log: DecisionLogSink
