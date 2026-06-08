"""
Assembles the orchestrator's ports for one run, entirely from the registry.

Adding or removing a tool/expert never edits this file: `discover()` populates the
registry from the tools/ and experts/ packages, and the generic handlers resolve
capabilities by key. Swapping an implementation (real memory, a different log
transport) is the only reason to touch this.
"""

from __future__ import annotations

from foundation import VrakshaContext
from core.memory import manager as memory_manager

from ..experts import ExpertHandler
from ..ports import Ports
from ..registry import discover
from ..tools import ToolHandler
from .decision_log import CtxDecisionLog


def build_default_ports(ctx: VrakshaContext) -> Ports:
    """Wire the Phase-1 ports: registry-backed handlers + memory door + sink."""
    discover()                                   # import tools/ and experts/ so they self-register
    tools = ToolHandler()                        # orchestrator-direct calls hold all grants
    experts = ExpertHandler(tools=tools)         # experts get scoped tool boxes
    return Ports(
        memory=memory_manager,
        experts=experts,
        tools=tools,
        log=CtxDecisionLog(ctx),
    )
