"""
Capabilities — the framework-agnostic gateway to tools and experts.

Open one Capabilities per request (bound to its ctx); it holds the guarded
tool/expert engines and the registry. `run_turn` runs one orchestrator turn as a
NATIVE tool-driving agent: every available tool + expert is offered to the model
as a guarded native tool — tool calls route through the ToolHandler; expert calls
route through the ExpertHandler (buffering full findings to ctx, returning a brief
summary to the model). The turn is bounded by UsageLimits (overridable per run),
streams a live decision log via `on_event`, and gracefully forces a final answer
at the cap.

The SDK never gets raw access: the tools are guarded wrappers, and all pydantic-ai
use lives in core/llm — this gateway only calls it.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable
from dataclasses import dataclass

from foundation import MaxRetriesExceededError, VrakshaContext

from .. import CapabilityKind, registry as default_registry
from .experts import ExpertHandler
from .tools import ToolHandler

_FORCE_ANSWER = (
    "\n\nYou have reached your tool/turn limit. Answer now using only what you "
    "already have; do not request any tools."
)


@dataclass(frozen=True)
class Capabilities:
    """The capability gateway (see module docstring). Open one per request."""

    ctx: VrakshaContext
    _tools: ToolHandler
    _experts: ExpertHandler

    @classmethod
    def open(cls, ctx: VrakshaContext, *, registry=default_registry) -> "Capabilities":
        """Open a full-power gateway for one request."""
        tools = ToolHandler(registry=registry)
        experts = ExpertHandler(registry=registry, tools=tools)
        return cls(ctx=ctx, _tools=tools, _experts=experts)

    @property
    def _registry(self):
        return self._tools._registry

    async def run_turn(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_type: type,
        on_event: Callable[[dict], Awaitable[None]] | None = None,
        max_turns: int | None = None,
        max_output_tokens: int | None = None,
        model: Any | None = None,
    ) -> Any:
        """
        Run one orchestrator turn as a native tool-driving agent.

        Every available tool + expert is offered to the model as a guarded native
        tool: tool calls route through this gateway's ToolHandler; expert calls
        route through its ExpertHandler (buffering full findings to ctx, returning a
        brief summary to the model — the two-output split as a tool return). Bounded
        by the orchestrator turn cap (overridable per run via `max_turns` /
        `max_output_tokens`), and streams a live decision log via `on_event`.
        Returns the model's structured `output_type`.

        At the turn/usage cap, gracefully forces ONE final answer with tools
        withheld; only if that still produces nothing do we fail closed
        (`MaxRetriesExceededError`). `model` overrides the model for this run (tests).
        """
        from core.llm import build_tool_agent, run_structured
        from .support import OrchestratorDeps, build_orchestrator_tools

        reg = self._registry
        tool_specs = [reg.get_tool(c["key"]) for c in reg.cards(CapabilityKind.TOOL)]
        expert_specs = [reg.get_expert(c["key"]) for c in reg.cards(CapabilityKind.EXPERT)]
        deps = OrchestratorDeps(ctx=self.ctx, tools=self._tools, experts=self._experts)

        handle = build_tool_agent(
            "orchestrator",
            output_type=output_type,
            system_prompt=system_prompt,
            tools=build_orchestrator_tools(tool_specs, expert_specs),
            deps_type=OrchestratorDeps,
        )
        try:
            return await run_structured(
                handle, user_prompt, deps=deps, on_tool_event=on_event,
                max_turns=max_turns, max_output_tokens=max_output_tokens, model=model,
            )
        except MaxRetriesExceededError:
            forced = build_tool_agent(
                "orchestrator",
                output_type=output_type,
                system_prompt=system_prompt + _FORCE_ANSWER,
                tools=[],
                deps_type=OrchestratorDeps,
            )
            return await run_structured(forced, user_prompt, deps=deps, max_turns=1, model=model)
