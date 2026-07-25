"""
Orchestrator-internal seams + the Ports bundle.

The loop dispatches through these; wiring assembles concrete impls. The
cross-layer MemoryPort lives in foundation; the capability door (Capabilities)
lives in registry.capabilities.handler — the orchestrator holds one, it does not
own it. Tool/expert calls all go through that single door, so there are no longer
separate tool/expert ports here.

Swapping a seam (a different decision-log transport, a different capability door)
means wiring a new value in build_default_ports — the loop never changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from foundation import BatchAwarenessPort, BudgetPort, GraphPort, MemoryPort

from .schemas import DecisionLogEntry

if TYPE_CHECKING:                       # type-only: keeps ports.py light (no SDK/security pull)
    from registry.capabilities.handler import Capabilities


@runtime_checkable
class DecisionLogSink(Protocol):
    """Where the loop streams decision-log entries; a richer transport can drop in."""

    async def emit(self, entry: DecisionLogEntry) -> None: ...


@dataclass
class Ports:
    """The seams the orchestrator loop depends on. Assembled by build_default_ports."""
    memory: MemoryPort
    caps: "Capabilities"        # the Flow-inspired tool/expert door
    log: DecisionLogSink
    # Defaulted + trailing so existing keyword-only test construction sites (Ports(memory=...,
    # caps=..., log=...)) keep working unchanged; None means "no awareness consumption" -- the
    # same fail-closed-to-no-op posture BatchHandler already has for a None awareness port.
    awareness: BatchAwarenessPort | None = None
    # Mission Engine loop-wiring (ratified 2026-07-25): both None means missions are simply
    # unavailable in this Ports instance (no start_mission/advance_mission/end_mission offered,
    # ctx.mission_id never set) -- the same gate-on-None idiom as awareness/batches. wiring.py's
    # real construction sets graph to the real GraphManager and budget to UnlimitedBudget (the
    # swap seam for backend's real Redis-backed anchor later -- see utils/unlimited_budget.py).
    graph: GraphPort | None = None
    budget: BudgetPort | None = None
