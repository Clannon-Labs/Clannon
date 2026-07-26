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

import settings
from foundation import BatchAwarenessPort, BudgetPort, GraphPort, MaxRetriesExceededError, VrakshaContext

from .. import CapabilityKind, registry as default_registry
from .batches import BatchDefinition, BatchHandler
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
    _allow_memory_write: bool = True   # gates the `remember` built-in; True preserves .open()'s behavior
    _batches: BatchHandler | None = None   # None for every scoped_to() instance -- see its docstring (recursion guard)
    # Mission Engine loop-wiring (ratified 2026-07-25): None for every scoped_to() instance too --
    # a batch's own scoped turn never starts/advances/ends a mission (that's the central
    # orchestrator's job coordinating the WHOLE mission), same recursion-guard shape as _batches.
    _graph: GraphPort | None = None
    _budget: BudgetPort | None = None

    @classmethod
    def open(
        cls, ctx: VrakshaContext, *, registry=default_registry,
        batch_registry: dict[str, BatchDefinition] | None = None,
        awareness: BatchAwarenessPort | None = None,
        graph: GraphPort | None = None,
        budget: BudgetPort | None = None,
    ) -> "Capabilities":
        """Open a full-power gateway for one request. `batch_registry` (batch_key
        -> BatchDefinition) is the ONLY construction site that can populate the
        batch tier -- see batches.py's module docstring on why `scoped_to()`
        deliberately has no equivalent parameter (a batch cannot spawn a batch).
        `awareness` (b1-item-3) is threaded the same way -- a batch's own scoped
        gateway needs no awareness handle, since it never calls spawn_batch itself.
        `graph`/`budget` (mission-engine loop-wiring) follow the same rule: only
        `.open()` can populate them, `scoped_to()` never does."""
        tools = ToolHandler(registry=registry)
        experts = ExpertHandler(registry=registry, tools=tools, graph=graph)
        batches = BatchHandler(batch_registry=batch_registry, registry=registry, awareness=awareness, graph=graph)
        return cls(ctx=ctx, _tools=tools, _experts=experts, _batches=batches, _graph=graph, _budget=budget)

    @classmethod
    def scoped_to(
        cls, ctx: VrakshaContext, *, expert_keys, tool_keys, grants,
        allow_memory_write: bool = False, graph: GraphPort | None = None, registry=default_registry,
    ) -> "Capabilities":
        """Open a gateway restricted to specific expert/tool keys and permission
        grants — for a batch orchestrator scoped to one domain (batch-orchestrator
        design v2, §B/§C). `expert_keys`/`tool_keys` are REQUIRED (no `None`-means-
        unrestricted default here, unlike the handlers' own `.scoped()`) — a caller
        must explicitly enumerate what a batch can reach, so an unrestricted batch
        is never accidental. Built from `ToolHandler`/`ExpertHandler`'s own
        compose-never-widen `.scoped()`, so this can be further narrowed safely
        (e.g. nesting) without ever escaping the scope requested here.

        `allow_memory_write` defaults to False (unlike `.open()`'s implicit True) —
        closes the ratified design's F2 finding one tier down: the central
        orchestrator's `remember` + unrestricted-NETWORK combination is a real
        exfiltration-surface risk this codebase never extended the "no memory +
        no egress together" rule to; a batch orchestrator's default is the safer
        posture, with per-batch config (once it exists) able to opt back in
        explicitly. `recall` (read-only, this session only) is unaffected — this
        gates the WRITE side only.

        `graph` (CB2 code-symbol tier, ratified 2026-07-26) is the SAME opt-in
        shape: `None` by default, explicitly passed by a caller that decided this
        particular batch should reach the graph (see `batches.py`'s per-`BatchDefinition
        .grants_graph` flag) — not bundled with the `_batches`/recursion-guard
        exclusion below, since reading/writing plain graph nodes carries none of
        that recursion risk (confirmed with backend before building this way).

        Deliberately takes no `batch_registry` param — `_batches` stays `None`
        on the returned instance, so a batch's own scoped gateway never offers
        `spawn_batch` to its own model (the recursion guard; see batches.py)."""
        tools = ToolHandler(registry=registry).scoped(allowed_keys=tool_keys, grants=grants)
        experts = ExpertHandler(registry=registry, tools=tools, graph=graph).scoped(allowed_keys=expert_keys)
        return cls(ctx=ctx, _tools=tools, _experts=experts, _allow_memory_write=allow_memory_write, _graph=graph)

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
        on_message: Callable[[str], Awaitable[None]] | None = None,
        max_turns: int | None = None,
        max_output_tokens: int | None = None,
        model: Any | None = None,
        conversation: Any | None = None,
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
        # workspace tools (fs.read/fs.write/code.run) need a per-run sandbox, so they
        # are expert-scoped and NOT offered to the orchestrator directly — it delegates
        # file/code work to an expert (e.g. code.engineer) that holds the workspace.
        tool_specs = [s for s in tool_specs if s and not getattr(s.impl, "wants_workspace", False)]
        expert_specs = [reg.get_expert(c["key"]) for c in reg.cards(CapabilityKind.EXPERT)]
        # A scoped gateway (Capabilities.scoped_to, for a batch orchestrator) must not
        # even OFFER an ungranted capability to the model — allowed_keys=None (the
        # unscoped/central case) leaves both lists untouched, matching today's behavior
        # exactly. The handlers themselves also refuse a call outside their scope
        # (defense in depth), but not offering it is the tighter, cleaner behavior.
        tool_allowed = self._tools._allowed_keys
        if tool_allowed is not None:
            tool_specs = [s for s in tool_specs if s.key in tool_allowed]
        expert_allowed = self._experts._allowed_keys
        if expert_allowed is not None:
            expert_specs = [s for s in expert_specs if s and s.key in expert_allowed]
        deps = OrchestratorDeps(
            ctx=self.ctx, tools=self._tools, experts=self._experts, batches=self._batches, model=model,
            graph=self._graph, budget=self._budget,
        )

        handle = build_tool_agent(
            "orchestrator",
            output_type=output_type,
            system_prompt=system_prompt,
            tools=build_orchestrator_tools(
                tool_specs, expert_specs, on_message=on_message,
                # when the user attached files this turn, surface the file-reading experts up
                # front so the orchestrator can actually read the upload (not fall back to search)
                files_attached=bool(getattr(self.ctx, "input_files", None)),
                with_memory_write=self._allow_memory_write,
                batches=self._batches,
                graph=self._graph, budget=self._budget,
            ),
            deps_type=OrchestratorDeps,
            retries=settings.ORCHESTRATOR.max_retries,
        )
        try:
            return await run_structured(
                handle, user_prompt, deps=deps, on_tool_event=on_event,
                max_turns=max_turns, max_output_tokens=max_output_tokens, model=model,
                conversation=conversation,
            )
        except MaxRetriesExceededError:
            forced = build_tool_agent(
                "orchestrator",
                output_type=output_type,
                system_prompt=system_prompt + _FORCE_ANSWER,
                tools=[],
                deps_type=OrchestratorDeps,
                retries=settings.ORCHESTRATOR.max_retries,
            )
            return await run_structured(
                forced, user_prompt, deps=deps, max_turns=1, model=model,
                conversation=conversation,
            )
