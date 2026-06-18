"""
Agent assembly: the tool-driving environments the expert and orchestrator run in.

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

The orchestrator is also a tool-driving agent (see below): its native tools are
every available tool + expert, each a guarded wrapper built by the same factory.

Skills + overlay resolution live in `skills.py` / `overlay.py`; the public skills
names are re-exported here so existing importers keep working.

This module intentionally does NOT use `from __future__ import annotations`: the
granted-tool wrappers carry a dynamic per-tool argument type that pydantic-ai must
introspect as a real type (via get_type_hints), not a deferred string.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from foundation import (
    MaxRetriesExceededError,
    MemoryStore,
    MemoryWriteProposal,
    ToolCallRecord,
    WorkspacePort,
    constants,
)
from core.llm import RunContext, Tool      # SDK types only via the core/llm boundary

from ..schemas import ExpertOutput, ExpertRequest, ToolRequest
from .overlay import expert_overlay_rel as _expert_overlay_rel, overlaid as _overlaid
from .skills import SkillBook, skills_hint

# Re-exported so importers of `support` (handler/__init__) keep working unchanged.
__all__ = [
    "ScopedToolbox",
    "ExpertDeps",
    "ExpertEnv",
    "SkillBook",
    "skills_hint",
    "load_skill",
    "build_expert_tools",
    "think",
    "OrchestratorDeps",
    "build_orchestrator_tools",
]


# ---------------------------------------------------------------------------
# Tool-wrapper factory — the orchestrator and each expert expose their granted
# capabilities to the model as thin async wrappers. All three wrapper kinds
# (expert tool, orchestrator tool, orchestrator expert) are identical except for
# the body that routes the call; that body is supplied as `invoke`. The model
# calls the wrapper with the capability's own input_schema, so the schema MUST be
# a real (non-deferred) annotation pydantic-ai can introspect.
# ---------------------------------------------------------------------------


def _make_wrapper(
    key: str,
    input_schema: type,
    description: str,
    *,
    invoke: Callable[[RunContext, object], Awaitable],
) -> Callable:
    """Build one model-facing tool wrapper. `invoke(ctx, args)` carries the only
    varying part (routing the call); everything else — the real `args:
    input_schema` annotation pydantic-ai introspects, the mangled tool name, and
    the description as docstring — is set identically for every wrapper."""

    async def wrapper(ctx: RunContext, args: input_schema):
        return await invoke(ctx, args)

    # The dynamic per-tool schema must reach pydantic-ai as a real type (it reads
    # __annotations__ via get_type_hints), so bind it explicitly on the wrapper.
    wrapper.__annotations__["args"] = input_schema
    wrapper.__name__ = key.replace(".", "_")
    wrapper.__doc__ = description
    return wrapper


# ---------------------------------------------------------------------------
# Expert run environment
# ---------------------------------------------------------------------------


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
    findings: list = field(default_factory=list)  # prior ExpertFindings, snapshot at spawn — lets a synthesis expert read full research by ref
    workspace: WorkspacePort | None = None  # per-run sandbox, if this expert is granted workspace tools; closed when the run ends
    input_files: list = field(default_factory=list)  # names of uploaded files seeded into the workspace for this run (set by the handler)


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

    async def invoke(ctx: RunContext[ExpertDeps], args) -> dict:
        if ctx.deps.tools is None:
            return {"error": "no tools granted to this expert"}
        record = await ctx.deps.tools.call(key, args.model_dump())
        return record.result if record.success else {"error": record.error}

    return _make_wrapper(key, input_schema, description, invoke=invoke)


def build_expert_tools(granted: list, skills: SkillBook) -> list[Callable]:
    """
    Build the tool set for an expert's agent: always `load_skill`, plus one
    wrapper per granted tool spec. `granted` is the granted tools' registry specs
    (the handler resolves them; support never imports the registry)."""
    tools: list[Callable] = [load_skill]
    for spec in granted:
        tools.append(_make_tool_fn(spec.key, spec.input_schema, spec.description))
    return tools


_EXPERT_FORCE_ANSWER = (
    "\n\nYou have reached your tool/turn limit. Return your ExpertOutput NOW using "
    "only the work you have already done; do not request any tools. Be honest about "
    "what you did and did not finish or verify, and lower confidence accordingly."
)


def _input_files_note(env: ExpertEnv) -> str:
    """A line telling the expert which uploaded files are already in its workspace,
    so it reads them with its file tools instead of assuming their contents. Empty
    when nothing was seeded (no uploads, or this expert has no workspace)."""
    names = getattr(env, "input_files", None)
    if not names:
        return ""
    return (
        "\n\nInput files for this task have been placed in your workspace: "
        f"{', '.join(names)}. Read them with your file tools — do not assume their contents."
    )


async def think(env: ExpertEnv, user_prompt: str, *, media=None) -> ExpertOutput:
    """Assemble the expert's agent from `env` and run it (it may call its tools /
    load skills) for an ExpertOutput, bounded to EXPERT_MAX_TURNS tool rounds.

    `media` is an optional list of (bytes, mime) attachments folded into the user
    message for a multimodal model (the media expert passes its images here).

    At the turn/usage cap, gracefully force ONE final answer with tools withheld —
    exactly as the orchestrator does — so a thorough expert returns its best
    ExpertOutput instead of failing hard."""
    from core.llm import build_tool_agent, run_structured
    from registry.config.prompts import read_overlay_text

    base_text, _source = read_overlay_text(
        _expert_overlay_rel(env.module_dir, "system.md"), env.module_dir / "system.md"
    )
    system_prompt = base_text + skills_hint(env.skills)
    # seeded uploads are task data, so they go on the user message, not the prompt
    user_prompt = user_prompt + _input_files_note(env)
    deps = ExpertDeps(skills=env.skills, tools=env.toolbox)

    def _agent(sys_prompt: str, tools: list) -> object:
        return build_tool_agent(
            env.model_role,
            output_type=ExpertOutput,
            system_prompt=sys_prompt,
            tools=tools,
            deps_type=ExpertDeps,
        )

    agent = _agent(system_prompt, build_expert_tools(env.granted, env.skills))
    try:
        return await run_structured(agent, user_prompt, deps=deps, max_turns=constants.EXPERT_MAX_TURNS, media=media)
    except MaxRetriesExceededError:
        forced = _agent(system_prompt + _EXPERT_FORCE_ANSWER, [])
        return await run_structured(forced, user_prompt, deps=deps, max_turns=1, media=media)


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

    async def invoke(ctx: RunContext[OrchestratorDeps], args) -> dict:
        record = await ctx.deps.tools.call_tool(
            ToolRequest(key=key, arguments=args.model_dump()), ctx.deps.ctx
        )
        return record.result if record.success else {"error": record.error}

    return _make_wrapper(key, input_schema, description, invoke=invoke)


def _make_orchestrator_expert_fn(key: str, input_schema: type, description: str) -> Callable:
    """Expose one expert to the orchestrator's model. The parameters ARE the
    expert's input_schema (which carries a required prompt), so the orchestrator
    always sends a real prompt. Full findings are buffered to ctx; the brief
    summary is returned to the model."""

    async def invoke(ctx: RunContext[OrchestratorDeps], args) -> str:
        summaries = await ctx.deps.experts.run_experts(
            [ExpertRequest(key=key, arguments=args.model_dump())], ctx.deps.ctx
        )
        if not summaries:
            return "[expert produced no result]"
        s = summaries[0]
        # the ref names the buffered full findings — pass it to a synthesis
        # expert (finding_refs) or deliver it directly (deliverable_ref)
        return f"[finding_ref: {s.finding_ref}] {s.summary}" if s.finding_ref else s.summary

    return _make_wrapper(key, input_schema, description, invoke=invoke)


def _make_say_tool(on_message: Callable) -> Callable:
    """The orchestrator's CONVERSATIONAL voice. `say(text)` hands `text` to the user
    immediately (a live chat message), so the orchestrator can talk WHILE experts work."""

    async def say(text: str) -> str:
        await on_message(text)
        return "shown to the user"

    say.__name__ = "say"
    say.__doc__ = (
        "Say something to the user right now, live (a conversational chat message). Use it "
        "to talk to the user while you work: briefly say what you are about to do before you "
        "spawn experts, share a caveat, or give a status update. This is your conversational "
        "voice and is shown to the user immediately. It is NOT the deliverable — put the "
        "actual result/report in your final answer. Args: text (what to say)."
    )
    return say


def _make_remember_tool() -> Callable:
    """A tool the orchestrator calls to save a durable fact or preference to long-term
    memory — when the user asks it to remember something, or when it learns something
    lasting about the user / how they work. It PROPOSES a high-confidence write (the
    Memory Manager still owns persistence); the orchestrator never touches the store."""

    async def remember(ctx: RunContext[OrchestratorDeps], content: str, kind: str = "fact") -> str:
        text = (content or "").strip()
        if not text:
            return "nothing to remember (empty content)"
        store = MemoryStore.PROCEDURAL if kind == "preference" else MemoryStore.SEMANTIC
        ctx.deps.ctx.memory_writes_requested.append(MemoryWriteProposal(
            store=store,
            content=text[:2000],
            rationale="user asked to remember it, or a durable fact the orchestrator chose to keep",
            confidence=0.95,   # high: an explicit, considered save — clears the write-policy floor
        ))
        return f"saved to long-term memory ({store.value})"

    remember.__name__ = "remember"
    remember.__doc__ = (
        "Save a durable fact or preference to your long-term memory so you recall it in "
        "FUTURE sessions. Call it when the user asks you to remember something, OR when you "
        "learn a lasting fact about the user, their work, or their domain, OR a clear "
        "preference for how they like things done. kind='fact' stores a fact (semantic); "
        "kind='preference' stores a way-of-working (procedural). Keep each entry to one "
        "self-contained sentence. Do NOT use it for this turn's transient details. Args: "
        "content (what to remember), kind ('fact' or 'preference')."
    )
    return remember


def _offer(fn: Callable, spec) -> "Callable | Tool":
    """Offer one capability to the orchestrator. A hot-path capability (`eager`) is
    passed as a bare function — in context from turn one. The long tail is wrapped as a
    deferred `Tool`: it stays OUT of the prompt (and out of the cached tool prefix) until
    the model discovers it via tool search, then becomes callable. Default is deferred,
    so the eager surface stays flat as the roster grows (W2)."""
    if getattr(spec, "eager", False):
        return fn
    return Tool(fn, defer_loading=True)


def build_orchestrator_tools(
    tool_specs: list, expert_specs: list, on_message: Callable | None = None
) -> list:
    """Native tools for the orchestrator agent: every available tool + expert as a
    guarded wrapper, plus the `remember` long-term-memory tool and (when a message sink
    is wired) the `say` conversational tool. The handler resolves the specs; support
    never imports the registry.

    `remember`/`say` and the hot-path (`eager`) capabilities load up front; the long
    tail is deferred behind tool search (W2). The framework auto-adds a `search_tools`
    function whenever any deferred capability is present, and the model pulls a
    capability into context only when it looks for one. Either way, every call still
    routes through the guarded handler on execution."""
    fns: list = [_make_remember_tool()]
    if on_message is not None:
        fns.append(_make_say_tool(on_message))
    for spec in tool_specs:
        fns.append(_offer(_make_orchestrator_tool_fn(spec.key, spec.input_schema, spec.description), spec))
    for spec in expert_specs:
        fns.append(_offer(_make_orchestrator_expert_fn(spec.key, spec.input_schema, spec.description), spec))
    return fns
