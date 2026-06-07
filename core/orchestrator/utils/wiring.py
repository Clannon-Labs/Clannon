"""
Assembles the default set of ports for one orchestrator run.

This is the single place that picks concrete implementations for each seam. To
move from stubs to real components (memory manager, experts, tools, entropy
router, a different log transport), swap the class chosen here — the loop and the
stage never change.
"""

from __future__ import annotations

from foundation import VrakshaContext
from core.memory import MemoryManager

from ..experts import StubExpertHandler
from ..ports import Ports
from ..tools import StubToolHandler
from .decision_log import QueueDecisionLogSink
from .router import DefaultExpertRouter


def build_default_ports(ctx: VrakshaContext) -> Ports:
    """Wire the Phase-1 ports (memory door + stub handlers + default router + sink)."""
    return Ports(
        memory=MemoryManager(),
        experts=StubExpertHandler(),
        tools=StubToolHandler(),
        router=DefaultExpertRouter(),
        log=QueueDecisionLogSink(ctx),
    )
