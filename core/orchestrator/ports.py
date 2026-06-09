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

from foundation import MemoryPort

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
