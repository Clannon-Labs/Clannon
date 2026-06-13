"""Verification expert (key: verification.claims) — checks factual claims against
their cited sources and independent evidence, flagging unsupported, contradicted,
misattributed, or hallucinated citations. Its behavior lives in its system prompt +
skills beside this file; this module declares what it is and how its input becomes
the agent's task."""

from __future__ import annotations

from pydantic import BaseModel, Field

from foundation import PermissionLevel

from registry import expert
from registry.capabilities import ExpertOutput
from registry.capabilities.handler import ExpertEnv, think


class VerifyIn(BaseModel):
    """What the orchestrator emits to call this expert (structured, not free text)."""
    prompt: str = Field(description="The claims or text whose factual claims should be verified, with any context.")
    sources: list[str] = Field(
        default_factory=list,
        description="Cited source URLs to check the claims against (if any). The expert "
        "also corroborates independently via web search.",
    )


@expert
class VerificationExpert:
    name = "claims"
    domain = "verification"
    description = "Verify factual claims against their cited sources and independent evidence; flag unsupported or hallucinated citations."
    input_schema = VerifyIn
    output_schema = ExpertOutput
    skills = ("skills",)                       # baseline skills/ beside this file
    tools = ("search.web", "web.fetch_url")    # REQUESTED; the handler grants them (scoped, guarded)
    model_role = "research"
    permission = PermissionLevel.NETWORK
    tags = ("verification", "citations", "fact-check")

    async def run(self, args: VerifyIn, env: ExpertEnv) -> ExpertOutput:
        return await think(env, _task(args, env))


def _task(args: VerifyIn, env: ExpertEnv) -> str:
    """Build this expert's per-call task: the claims to verify plus any cited
    sources to check them against."""
    cited = "\n".join(f"- {s}" for s in args.sources) if args.sources else "(none provided — corroborate independently)"
    return (
        "Verify the factual claims in the following.\n\n"
        f"## Claims / text to verify\n{args.prompt}\n\n"
        f"## Cited sources to check against\n{cited}"
    )
