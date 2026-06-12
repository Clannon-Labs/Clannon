"""
Generic expert handler — registry-driven, zero per-expert wiring.

Looks an expert up by key, validates the structured arguments against its
input_schema, assembles its run materials (a SkillBook + a scoped tool box +
its granted tool specs), runs it under concurrency + timeout bounds, and enforces
the two-output contract: a brief ExpertSummary goes back to the orchestrator while
the full ExpertFindings is buffered on the context for the output filter. Each
result is *marked* (success, confidence, a small quality signal) on the
ExpertCallRecord for future performance-based routing. Unknown/broken/failed
experts return a failed summary, never silence.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from pathlib import Path
from uuid import uuid4

from foundation import ExpertCallRecord, PermissionLevel, VrakshaContext, constants

from .. import CapabilityKind, registry as default_registry
from ..schemas import ExpertFindings, ExpertRequest, ExpertSummary
from .support import ExpertEnv, ScopedToolbox, SkillBook


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

            # Structured invocation: the arguments must satisfy the expert's
            # input_schema — never free-form text.
            try:
                args = spec.input_schema(**request.arguments)
            except Exception as exc:
                return self._fail(request, ctx, started, f"bad arguments: {exc}")

            env = self._build_env(spec, ctx)
            try:
                output = await asyncio.wait_for(
                    spec.impl().run(args, env), timeout=constants.EXPERT_TIMEOUT_S
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
                    arguments=dict(request.arguments),
                    result={"finding_ref": ref, "mark": _mark(output)},
                    success=True,
                    duration_ms=round((time.monotonic() - started) * 1000, 2),
                )
            )
            return ExpertSummary(
                expert=spec.key, summary=output.summary,
                confidence=output.confidence, finding_ref=ref,
            )

    def _build_env(self, spec, ctx: VrakshaContext) -> ExpertEnv:
        """Pack the expert's run materials; the agent itself is assembled in think()."""
        module_dir = Path(inspect.getfile(spec.impl)).parent
        skills = SkillBook(module_dir, spec.skills)
        granted = [s for s in (self._registry.get_tool(k) for k in spec.tool_grants) if s is not None]
        return ExpertEnv(
            module_dir=module_dir,
            model_role=spec.model_role,
            skills=skills,
            toolbox=self._toolbox_for(granted, ctx),
            granted=granted,
            findings=list(ctx.expert_findings),
        )

    def _toolbox_for(self, granted: list, ctx: VrakshaContext) -> ScopedToolbox | None:
        """A tool box scoped to the expert's granted tool keys, or None if it has none."""
        if self._tools is None or not granted:
            return None
        grants = {PermissionLevel.READ}
        for spec in granted:
            grants.add(spec.permission)
        scoped = self._tools.scoped(
            allowed_keys={spec.key for spec in granted}, grants=frozenset(grants)
        )
        return ScopedToolbox(scoped, ctx)

    def _fail(self, request, ctx, started, reason) -> ExpertSummary:
        ctx.expert_calls.append(
            ExpertCallRecord(
                expert_name=request.key, arguments=dict(request.arguments),
                result=None, success=False,
                duration_ms=round((time.monotonic() - started) * 1000, 2),
                error=reason,
            )
        )
        return ExpertSummary(expert=request.key, summary=f"[unavailable] {reason}", confidence=0.0, finding_ref="")


def _mark(output) -> dict:
    """A small quality signal recorded per result for future routing/diagnosis."""
    return {
        "confidence": output.confidence,
        "has_citations": bool(output.citations),
        "length": len(output.full_content or ""),
    }
