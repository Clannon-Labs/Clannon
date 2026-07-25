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
from core.memory.batch_awareness_manager import manager as batch_awareness_manager
from core.memory.graph_manager import manager as graph_manager
from registry.capabilities import discover

from ..ports import Ports
from .decision_log import CtxDecisionLog
from .unlimited_budget import UnlimitedBudget

# Mission Engine loop-wiring (ratified 2026-07-25): the swap seam for backend's real
# Redis-backed budget anchor -- see unlimited_budget.py's own docstring. Module-level
# singleton (not per-run) since it holds no state; UnlimitedBudget() would be equally
# correct constructed fresh each call.
_unlimited_budget = UnlimitedBudget()


def build_default_ports(ctx: VrakshaContext) -> Ports:
    """Wire the Phase-1 ports: the capability door + memory door + decision-log sink."""
    # Imported lazily: both depend on the handler package, which itself depends on
    # core.llm -- importing at module load would re-enter core/__init__ ->
    # orchestrator -> wiring (a cycle).
    from registry.capabilities.handler import Capabilities
    from registry.config.batches import load_batches

    discover()                              # import tools/ and experts/ so they self-register
    return Ports(
        memory=memory_manager,
        awareness=batch_awareness_manager,
        graph=graph_manager,
        budget=_unlimited_budget,
        caps=Capabilities.open(
            ctx, batch_registry=load_batches(), awareness=batch_awareness_manager,
            graph=graph_manager, budget=_unlimited_budget,
        ),   # one door; tool/expert calls + guards inside
        log=CtxDecisionLog(ctx),
    )
