"""
Assembles the orchestrator's ports for one run.

Adding or removing a tool/expert never edits this file: `discover()` populates the
capability registry from the tools/ and experts/ packages, and the Capabilities
door resolves capabilities by key. Swapping an implementation (real memory, a
different log transport) is the only reason to touch this.
"""

from __future__ import annotations

from foundation import VrakshaContext
from core.memory import manager as memory_manager
from registry.capabilities import discover

from ..ports import Ports
from .decision_log import CtxDecisionLog


def build_default_ports(ctx: VrakshaContext) -> Ports:
    """Wire the Phase-1 ports: the capability door + memory door + decision-log sink."""
    # Imported lazily: the handler depends on core.llm, so importing it at module
    # load would re-enter core/__init__ -> orchestrator -> wiring (a cycle).
    from registry.capabilities.handler import Capabilities

    discover()                              # import tools/ and experts/ so they self-register
    return Ports(
        memory=memory_manager,
        caps=Capabilities.open(ctx),        # one door; tool/expert calls + guards inside
        log=CtxDecisionLog(ctx),
    )
