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
from .sandbox import DockerWorkspace
from .support import ExpertEnv, ScopedToolbox, SkillBook

_MAX_ARTIFACTS = 20                       # max output artifacts captured per expert run
_MAX_ARTIFACT_BYTES = 10 * 1024 * 1024    # 10 MB cap per artifact


class ExpertHandler:
    """Implements ExpertHandlerPort over the capability registry."""

    def __init__(self, registry=default_registry, tools=None, artifact_store=None) -> None:
        self._registry = registry
        self._tools = tools                          # a ToolHandler, for scoping
        self._artifacts = artifact_store             # an ArtifactStore; lazy LocalArtifactStore if None
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
                # seed any uploaded input files into this expert's workspace before
                # it runs (no-op unless it has a workspace and the run carried files)
                await self._seed_inputs(env, ctx)
                try:
                    output = await asyncio.wait_for(
                        spec.impl().run(args, env), timeout=constants.EXPERT_TIMEOUT_S
                    )
                except asyncio.TimeoutError:
                    return self._fail(request, ctx, started, "expert timed out")
                except Exception as exc:
                    return self._fail(request, ctx, started, f"expert error: {exc}")

                ref = uuid4().hex[:8]
                # capture designated output artifacts out of the workspace BEFORE it
                # is torn down (the finally below closes it)
                artifacts = await self._capture_artifacts(output, env, ctx)
                ctx.expert_findings.append(
                    ExpertFindings(
                        expert=spec.key, ref=ref, full_content=output.full_content,
                        citations=list(output.citations),
                        metadata={"confidence": output.confidence, "artifacts": artifacts},
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
            finally:
                # the per-run sandbox dies when the work is done (success or fail)
                if env.workspace is not None:
                    await env.workspace.close()

    def _build_env(self, spec, ctx: VrakshaContext) -> ExpertEnv:
        """Pack the expert's run materials; the agent itself is assembled in think()."""
        module_dir = Path(inspect.getfile(spec.impl)).parent
        skills = SkillBook(module_dir, spec.skills)
        granted = [s for s in (self._registry.get_tool(k) for k in spec.tool_grants) if s is not None]
        # spin up a per-run sandbox only if this expert is actually granted a
        # workspace tool (and there's a tool handler to route through). Cheap until
        # first use — the Docker container is lazy; the temp dir is wiped on close.
        needs_ws = self._tools is not None and any(getattr(s.impl, "wants_workspace", False) for s in granted)
        workspace = DockerWorkspace() if needs_ws else None
        return ExpertEnv(
            module_dir=module_dir,
            model_role=spec.model_role,
            skills=skills,
            toolbox=self._toolbox_for(granted, ctx, workspace),
            granted=granted,
            findings=list(ctx.expert_findings),
            workspace=workspace,
        )

    def _toolbox_for(self, granted: list, ctx: VrakshaContext, workspace=None) -> ScopedToolbox | None:
        """A tool box scoped to the expert's granted tool keys (bound to its per-run
        workspace), or None if it has none."""
        if self._tools is None or not granted:
            return None
        grants = {PermissionLevel.READ}
        for spec in granted:
            grants.add(spec.permission)
        scoped = self._tools.scoped(
            allowed_keys={spec.key for spec in granted}, grants=frozenset(grants), workspace=workspace
        )
        return ScopedToolbox(scoped, ctx)

    async def _seed_inputs(self, env, ctx: VrakshaContext) -> None:
        """Place the run's uploaded input files into this expert's workspace so it
        can read them with its file tools. No-op unless the expert actually has a
        workspace and the run carried files. Records the seeded names on the env so
        think() can tell the expert they're there. Best-effort per file."""
        files = list(getattr(ctx, "input_files", None) or [])
        if env.workspace is None or not files:
            return
        seeded: list[str] = []
        for f in files:
            try:
                await env.workspace.write_bytes(f.name, f.data)
                seeded.append(f.name)
            except Exception:  # noqa: BLE001 — one bad file must not sink the run
                continue
        env.input_files = seeded

    async def _capture_artifacts(self, output, env, ctx: VrakshaContext) -> list[dict]:
        """Copy the expert's designated output files out of the (about-to-be-closed)
        workspace into durable storage; return their references as dicts. Best-effort:
        a missing, oversized, or unreadable artifact is skipped, never fatal."""
        paths = list(getattr(output, "artifacts", None) or [])
        if not paths or env.workspace is None:
            return []
        store = self._artifacts
        if store is None:
            from core.artifacts import LocalArtifactStore
            store = self._artifacts = LocalArtifactStore()
        refs: list[dict] = []
        for path in paths[:_MAX_ARTIFACTS]:
            try:
                data = await env.workspace.read_bytes(path)
            except Exception:  # noqa: BLE001 — designated file missing/unreadable -> skip
                continue
            if len(data) > _MAX_ARTIFACT_BYTES:
                continue
            try:
                name = str(path).replace("\\", "/").split("/")[-1]
                refs.append((await store.put(ctx.trace_id, name, data)).as_dict())
            except Exception:  # noqa: BLE001
                continue
        return refs

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
