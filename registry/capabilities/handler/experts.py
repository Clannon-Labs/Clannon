"""
Generic expert handler — registry-driven, zero per-expert wiring.

Looks an expert up by key, assembles its mini-environment (skills + a scoped tool
box), runs it under concurrency + timeout bounds, and enforces the two-output
contract: a brief ExpertSummary goes back to the orchestrator while the full
ExpertFindings is buffered on the context for the output filter. Each result is
*marked* (success, confidence, a small quality signal) on the ExpertCallRecord for
future performance-based routing. Unknown/broken/failed experts return a failed
summary, never silence.
"""

from __future__ import annotations

import asyncio
import time
from uuid import uuid4

from foundation import ExpertCallRecord, PermissionLevel, VrakshaContext, constants

from ..registry import CapabilityKind, registry as default_registry
from ..schemas import ExpertFindings, ExpertOutput, ExpertRequest, ExpertSummary
from .support import ExpertEnv, ScopedToolbox, load_skills


class ExpertHandler:
    """Implements ExpertHandlerPort over the capability registry."""

    def __init__(self, registry=default_registry, tools=None) -> None:
        self._registry = registry
        self._tools = tools                          # a ToolHandler, for scoping
        self._semaphore = asyncio.Semaphore(constants.EXPERT_MAX_CONCURRENT)

    async def run_experts(
        self, requests: list[ExpertRequest], ctx: VrakshaContext
    ) -> list[ExpertSummary]:
        if not requests:
            return []
        return await asyncio.gather(*[self._run_one(req, ctx) for req in requests])

    async def _run_one(self, request: ExpertRequest, ctx: VrakshaContext) -> ExpertSummary:
        async with self._semaphore:
            started = time.monotonic()
            spec = self._registry.get_expert(request.key)
            if spec is None:
                reason = self._registry.describe_missing(CapabilityKind.EXPERT, request.key)
                return self._fail(request, ctx, started, reason)

            env = ExpertEnv(
                prompt_name=spec.prompt_name,
                model_role=spec.model_role,
                skills=load_skills(spec.impl, spec.skills),
                tools=self._toolbox_for(spec, ctx),
            )
            try:
                output: ExpertOutput = await asyncio.wait_for(
                    spec.impl().run(request.task, env), timeout=constants.EXPERT_TIMEOUT_S
                )
            except asyncio.TimeoutError:
                return self._fail(request, ctx, started, "expert timed out")
            except Exception as exc:
                return self._fail(request, ctx, started, f"expert error: {exc}")

            ref = uuid4().hex[:8]
            ctx.expert_findings.append(
                ExpertFindings(
                    expert=spec.key, ref=ref, full_content=output.full_content,
                    citations=list(output.citations), metadata={"confidence": output.confidence},
                )
            )
            ctx.expert_calls.append(
                ExpertCallRecord(
                    expert_name=spec.key,
                    arguments={"task": request.task},
                    result={"finding_ref": ref, "mark": _mark(output)},
                    success=True,
                    duration_ms=round((time.monotonic() - started) * 1000, 2),
                )
            )
            return ExpertSummary(
                expert=spec.key, summary=output.summary,
                confidence=output.confidence, finding_ref=ref,
            )

    def _toolbox_for(self, spec, ctx: VrakshaContext) -> ScopedToolbox | None:
        """A tool box scoped to the expert's granted tool keys, or None if it has none."""
        if self._tools is None or not spec.tool_grants:
            return None
        grants = {PermissionLevel.READ}
        for key in spec.tool_grants:
            tool_spec = self._registry.get_tool(key)
            if tool_spec is not None:
                grants.add(tool_spec.permission)
        scoped = self._tools.scoped(allowed_keys=set(spec.tool_grants), grants=frozenset(grants))
        return ScopedToolbox(scoped, ctx)

    def _fail(self, request, ctx, started, reason) -> ExpertSummary:
        ctx.expert_calls.append(
            ExpertCallRecord(
                expert_name=request.key, arguments={"task": request.task},
                result=None, success=False,
                duration_ms=round((time.monotonic() - started) * 1000, 2),
                error=reason,
            )
        )
        return ExpertSummary(expert=request.key, summary=f"[unavailable] {reason}", confidence=0.0, finding_ref="")


def _mark(output: ExpertOutput) -> dict:
    """A small quality signal recorded per result for future routing/diagnosis."""
    return {
        "confidence": output.confidence,
        "has_citations": bool(output.citations),
        "length": len(output.full_content or ""),
    }
