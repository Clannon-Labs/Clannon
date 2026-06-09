"""
Expert support: the tool-driving environment an expert runs in.

An expert is a real agent. Its model gets a `load_skill` tool plus thin wrappers
over its granted tools, and decides for itself when to pull a skill or call a
tool — nothing is dumped into its context up front (the co-located system prompt
carries the always-on behaviour; skills are loaded on demand). Every tool call,
including the expert's own, routes through the scoped ToolHandler against the real
ctx, so all guards (permission, SSRF, NETWORK-output sanitization, output cap)
hold and the calls are audited on ctx.tool_calls.

The handler packs the run materials into `ExpertEnv`; `think()` assembles the
agent from them. An expert that never calls `think()` (e.g. a test fake) builds
no model and reads no prompt.

This module intentionally does NOT use `from __future__ import annotations`: the
granted-tool wrappers carry a dynamic per-tool argument type that pydantic-ai
must introspect as a real type, not a deferred string.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from foundation import ToolCallRecord, constants
from core.llm import RunContext      # SDK types only via the core/llm boundary

from ..schemas import ExpertOutput, ExpertRequest, ToolRequest


# ---------------------------------------------------------------------------
# Skills — loaded on demand, never dumped into context
# ---------------------------------------------------------------------------

class SkillBook:
    """
    The skills available to an expert, resolved beside its module.

    Each entry in the expert's `skills=(...)` is a `.md` file or a folder (whose
    `.md` files are all offered), located beside the expert. Skills are read
    lazily by name via `load()`; `names()` lists what's available so the expert
    knows what it can pull.
    """

    def __init__(self, base_dir: Path, entries: tuple[str, ...]) -> None:
        self._index: dict[str, Path] = {}
        for entry in entries:
            path = base_dir / entry
            if path.is_dir():
                for md in sorted(path.glob("*.md")):
                    self._index[md.stem] = md
            elif path.is_file():
                self._index[path.stem] = path

    def names(self) -> list[str]:
        """Skill names this expert may load."""
        return sorted(self._index)

    def load(self, name: str) -> str:
        """Read one skill by name, or a clear not-found note."""
        path = self._index.get(name)
        if path is None:
            return f"[no skill named {name!r}; available: {', '.join(self.names()) or 'none'}]"
        return path.read_text(encoding="utf-8").strip()


class ScopedToolbox:
    """A by-key tool caller restricted to an expert's granted tools, bound to the
    real ctx so calls go through the scoped ToolHandler and are audited normally."""

    def __init__(self, handler, ctx) -> None:
        self._handler = handler
        self._ctx = ctx

    async def call(self, key: str, arguments: dict) -> ToolCallRecord:
        return await self._handler.call_tool(ToolRequest(key=key, arguments=arguments), self._ctx)


@dataclass
class ExpertDeps:
    """Per-run handles the expert's tools read through RunContext.deps."""
    skills: SkillBook
    tools: ScopedToolbox | None = None


@dataclass
class ExpertEnv:
    """Materials the handler hands an expert; `think()` assembles the agent from them."""
    module_dir: Path
    model_role: str
    skills: SkillBook
    toolbox: ScopedToolbox | None
    granted: list   # granted tools' registry specs (key, input_schema, description)


# ---------------------------------------------------------------------------
# Tool functions handed to the expert's agent
# ---------------------------------------------------------------------------

async def load_skill(ctx: RunContext[ExpertDeps], name: str) -> str:
    """Load one of your skills by name and return its text. Call this only when a
    skill is relevant — skills are reference material, not always in context."""
    return ctx.deps.skills.load(name)


def _make_tool_fn(key: str, input_schema: type, description: str) -> Callable:
    """A thin wrapper exposing a granted tool to the expert's model. The model
    calls it with the tool's own input schema; the call routes through the scoped
    handler (all guards apply). Returns the tool's structured result or an error."""

    async def call_tool(ctx: RunContext[ExpertDeps], args: input_schema) -> dict:
        if ctx.deps.tools is None:
            return {"error": "no tools granted to this expert"}
        record = await ctx.deps.tools.call(key, args.model_dump())
        return record.result if record.success else {"error": record.error}

    call_tool.__name__ = key.replace(".", "_")
    call_tool.__doc__ = description
    return call_tool


def build_expert_tools(granted: list, skills: SkillBook) -> list[Callable]:
    """
    Build the tool set for an expert's agent: always `load_skill`, plus one
    wrapper per granted tool spec. `granted` is the granted tools' registry specs
    (the handler resolves them; support never imports the registry)."""
    tools: list[Callable] = [load_skill]
    for spec in granted:
        tools.append(_make_tool_fn(spec.key, spec.input_schema, spec.description))
    return tools


def skills_hint(skills: SkillBook) -> str:
    """A short instruction appended to the system prompt so the expert knows which
    skills exist and how to pull them."""
    names = skills.names()
    if not names:
        return ""
    return (
        "\n\nYour loadable skills: "
        + ", ".join(names)
        + ". Call load_skill(name) to read one when it is relevant; do not assume "
        "its contents otherwise."
    )


async def think(env: ExpertEnv, user_prompt: str) -> ExpertOutput:
    """Assemble the expert's agent from `env` and run it (it may call its tools /
    load skills) for an ExpertOutput, bounded to EXPERT_MAX_TURNS tool rounds."""
    from core.llm import build_tool_agent, run_structured

    system_prompt = (env.module_dir / "system.md").read_text(encoding="utf-8").strip() + skills_hint(env.skills)
    agent = build_tool_agent(
        env.model_role,
        output_type=ExpertOutput,
        system_prompt=system_prompt,
        tools=build_expert_tools(env.granted, env.skills),
        deps_type=ExpertDeps,
    )
    deps = ExpertDeps(skills=env.skills, tools=env.toolbox)
    return await run_structured(agent, user_prompt, deps=deps, max_turns=constants.EXPERT_MAX_TURNS)


# ---------------------------------------------------------------------------
# Orchestrator support — the orchestrator is also a tool-driving agent. Its
# native tools are every available tool + expert, each a guarded wrapper. Tool
# calls route through the (full-grant) ToolHandler; expert calls route through the
# ExpertHandler, which buffers full findings to ctx and returns only the brief
# summary to the model (the two-output split, as a tool return).
# ---------------------------------------------------------------------------

@dataclass
class OrchestratorDeps:
    """Per-run handles the orchestrator's native tools read through RunContext.deps."""
    ctx: object
    tools: object       # ToolHandler (full grants)
    experts: object     # ExpertHandler


def _make_orchestrator_tool_fn(key: str, input_schema: type, description: str) -> Callable:
    """Expose one tool to the orchestrator's model; routes through the guarded
    ToolHandler and records on ctx.tool_calls."""

    async def call_tool(ctx: RunContext[OrchestratorDeps], args: input_schema) -> dict:
        record = await ctx.deps.tools.call_tool(
            ToolRequest(key=key, arguments=args.model_dump()), ctx.deps.ctx
        )
        return record.result if record.success else {"error": record.error}

    call_tool.__name__ = key.replace(".", "_")
    call_tool.__doc__ = description
    return call_tool


def _make_orchestrator_expert_fn(key: str, input_schema: type, description: str) -> Callable:
    """Expose one expert to the orchestrator's model. The parameters ARE the
    expert's input_schema (which carries a required prompt), so the orchestrator
    always sends a real prompt. Full findings are buffered to ctx; the brief
    summary is returned to the model."""

    async def spawn_expert(ctx: RunContext[OrchestratorDeps], args: input_schema) -> str:
        summaries = await ctx.deps.experts.run_experts(
            [ExpertRequest(key=key, arguments=args.model_dump())], ctx.deps.ctx
        )
        return summaries[0].summary if summaries else "[expert produced no result]"

    spawn_expert.__name__ = key.replace(".", "_")
    spawn_expert.__doc__ = description
    return spawn_expert


def build_orchestrator_tools(tool_specs: list, expert_specs: list) -> list[Callable]:
    """Native tools for the orchestrator agent: every available tool + expert as a
    guarded wrapper. The handler resolves the specs; support never imports the
    registry."""
    fns: list[Callable] = []
    for spec in tool_specs:
        fns.append(_make_orchestrator_tool_fn(spec.key, spec.input_schema, spec.description))
    for spec in expert_specs:
        fns.append(_make_orchestrator_expert_fn(spec.key, spec.input_schema, spec.description))
    return fns
