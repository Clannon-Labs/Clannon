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

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from foundation import ToolCallRecord, constants
from core.llm import RunContext      # SDK types only via the core/llm boundary

from ..schemas import ExpertOutput, ExpertRequest, ToolRequest


# ---------------------------------------------------------------------------
# Prompt overlay — an expert's system.md and skills are co-located beside its
# code (the committed baseline), but their production text can be supplied out of
# git via the same overlay folder the registry prompts use. These helpers map an
# expert file to its overlay-relative path and resolve overlay-first. (Imports are
# local to dodge any package import-order edge.)
# ---------------------------------------------------------------------------


def _expert_overlay_rel(module_dir: Path, *parts: str) -> str:
    """Overlay-relative path for an expert file, mirroring its repo layout
    (e.g. experts/web_research/system.md). Falls back to the bare dir name if the
    module somehow sits outside the repo root."""
    from registry.config.prompts import REPO_ROOT

    try:
        rel = module_dir.resolve().relative_to(REPO_ROOT)
    except ValueError:
        rel = Path(module_dir.name)
    return rel.joinpath(*parts).as_posix()


def _overlaid(module_dir: Path, baseline: Path) -> Path:
    """Resolve one expert file (system.md or a skill) through the prompt overlay:
    the production text wins, the committed file is the fallback."""
    from registry.config.prompts import resolve_overlay

    rel = _expert_overlay_rel(module_dir, *baseline.relative_to(module_dir).parts)
    path, _source = resolve_overlay(rel, baseline)
    return path


# ---------------------------------------------------------------------------
# Skills — loaded on demand, never dumped into context
# ---------------------------------------------------------------------------

@dataclass
class _Skill:
    """One resolved skill: its name, a short when-to-use description (from the
    file's optional frontmatter), and its body (the full guide, handed over on
    demand)."""
    name: str
    description: str
    body: str


def _parse_skill(path: Path) -> tuple[str, str]:
    """Split a skill file into (description, body).

    The description comes from an optional `---`-delimited frontmatter
    `description:` line; it is surfaced up front so the expert can pick a skill
    WITHOUT loading its body. The body is the full guide handed over only on
    load_skill(). A file with no frontmatter has an empty description and is its
    own body.
    """
    text = path.read_text(encoding="utf-8").strip()
    if not text.startswith("---"):
        return "", text
    end = text.find("\n---", 3)
    if end == -1:
        return "", text
    frontmatter, body = text[3:end], text[end + 4:].strip()
    description = ""
    for line in frontmatter.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("description:"):
            description = stripped.split(":", 1)[1].strip().strip('"').strip("'")
            break
    return description, body


class SkillBook:
    """
    The skills available to an expert, resolved beside its module.

    Each entry in the expert's `skills=(...)` is a `.md` file or a folder (whose
    `.md` files are all offered), located beside the expert. Progressive
    disclosure: only each skill's name + short description is surfaced to the
    expert up front (see skills_hint); the full body is handed over only when the
    expert calls `load()`. This keeps context lean as the skill set grows.
    """

    def __init__(self, base_dir: Path, entries: tuple[str, ...]) -> None:
        # The SET of skills is defined by the committed files beside the expert;
        # each is then resolved through the prompt overlay (prod text wins, the
        # committed file is the fallback), so the overlay can harden a skill but
        # never introduce one. Each file is read once here to split its up-front
        # description from its on-demand body — the body is NOT put in context now.
        self._skills: dict[str, _Skill] = {}
        for entry in entries:
            path = base_dir / entry
            if path.is_dir():
                files = sorted(path.glob("*.md"))
            elif path.is_file():
                files = [path]
            else:
                files = []
            for md in files:
                description, body = _parse_skill(_overlaid(base_dir, md))
                self._skills[md.stem] = _Skill(md.stem, description, body)

    def names(self) -> list[str]:
        """Skill names this expert may load."""
        return sorted(self._skills)

    def catalog(self) -> list[tuple[str, str]]:
        """(name, description) per skill — what's surfaced up front so the expert
        can choose a skill to load without seeing its body."""
        return [(name, self._skills[name].description) for name in sorted(self._skills)]

    def load(self, name: str) -> str:
        """Return one skill's full body by name, or a clear not-found note."""
        skill = self._skills.get(name)
        if skill is None:
            return f"[no skill named {name!r}; available: {', '.join(self.names()) or 'none'}]"
        return skill.body


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
    skills exist and WHEN to pull each one. Only names + descriptions go here; the
    full skill body is handed over on demand via load_skill (progressive
    disclosure), so this stays small as the skill set grows."""
    catalog = skills.catalog()
    if not catalog:
        return ""
    listing = "\n".join(
        f"- {name}: {desc}" if desc else f"- {name}" for name, desc in catalog
    )
    return (
        "\n\nYou have loadable skills — reference guides that are NOT yet in your "
        "context. Each is listed below as `name: when to use it`. Call "
        "load_skill(name) to read a skill's full guide ONLY when it is relevant to "
        "the current step; do not assume its contents otherwise:\n" + listing
    )


async def think(env: ExpertEnv, user_prompt: str) -> ExpertOutput:
    """Assemble the expert's agent from `env` and run it (it may call its tools /
    load skills) for an ExpertOutput, bounded to EXPERT_MAX_TURNS tool rounds."""
    from core.llm import build_tool_agent, run_structured
    from registry.config.prompts import read_overlay_text

    base_text, _source = read_overlay_text(
        _expert_overlay_rel(env.module_dir, "system.md"), env.module_dir / "system.md"
    )
    system_prompt = base_text + skills_hint(env.skills)
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
        if not summaries:
            return "[expert produced no result]"
        s = summaries[0]
        # the ref names the buffered full findings — pass it to a synthesis
        # expert (finding_refs) or deliver it directly (deliverable_ref)
        return f"[finding_ref: {s.finding_ref}] {s.summary}" if s.finding_ref else s.summary

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
