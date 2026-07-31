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
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import settings
from foundation import ExpertCallRecord, GraphPort, PermissionLevel, ToolCallRecord, VrakshaContext

from .. import CapabilityKind, registry as default_registry
from ..schemas import ExpertFindings, ExpertRequest, ExpertSummary
from . import code_symbols
from .sandbox import DockerWorkspace
from .support import ExpertEnv, ScopedToolbox, SkillBook
from .workspace_archive import (
    mission_workspace_key as _mission_workspace_key,
    snapshot_workspace as _snapshot_workspace,
    validate_archive_members as _validate_archive_members,
    write_members as _write_members,
)
from .workspace_transactions import _WORKSPACE_TRANSACTIONS


class ExpertHandler:
    """Implements ExpertHandlerPort over the capability registry."""

    def __init__(
        self, registry=default_registry, tools=None, artifact_store=None, allowed_keys=None,
        graph: GraphPort | None = None,
    ) -> None:
        self._registry = registry
        self._tools = tools                          # a ToolHandler, for scoping
        self._artifacts = artifact_store             # an ArtifactStore; lazy LocalArtifactStore if None
        self._graph = graph                          # a GraphPort; None unless explicitly opted in (CB2 symbol tier)
        self._semaphore = asyncio.Semaphore(settings.EXPERTS.max_concurrent)
        self._allowed_keys = None if allowed_keys is None else frozenset(allowed_keys)

    def scoped(self, allowed_keys) -> "ExpertHandler":
        """A handler restricted to specific expert keys (for a batch orchestrator) —
        mirrors `ToolHandler.scoped()`, including its compose-never-widen discipline:
        an already-scoped handler's `.scoped()` can only narrow further. Shares this
        handler's `tools`/`artifact_store`/`graph` so a scoped expert still gets a
        correctly (and, via `ToolHandler.scoped()`'s own intersection, correctly
        NARROWED) scoped toolbox through `_toolbox_for`."""
        narrowed = (
            allowed_keys if self._allowed_keys is None
            else self._allowed_keys if allowed_keys is None
            else self._allowed_keys & frozenset(allowed_keys)
        )
        return ExpertHandler(
            self._registry, tools=self._tools, artifact_store=self._artifacts,
            graph=self._graph, allowed_keys=narrowed,
        )

    async def run_experts(
        self, requests: list[ExpertRequest], ctx: VrakshaContext
    ) -> list[ExpertSummary]:
        if not requests:
            return []
        return await asyncio.gather(*[self._run_one(req, ctx) for req in requests])

    async def _run_one(self, request: ExpertRequest, ctx: VrakshaContext) -> ExpertSummary:
        async with self._semaphore:
            started = time.monotonic()
            # `spec.permission` is NOT checked here — it's catalog-only for experts
            # (see ExpertSpec's docstring in ../specs.py). Access control is `spec.
            # tool_grants`, scoped below in `_build_env`/`_toolbox_for`, PLUS this
            # handler's own `_allowed_keys` (checked just below) — the gate a
            # reduced-privilege caller (a batch orchestrator's scoped Capabilities)
            # actually depends on, via `.scoped()`.
            spec = self._registry.get_expert(request.key)
            if spec is None:
                reason = self._registry.describe_missing(CapabilityKind.EXPERT, request.key)
                return self._fail(request, ctx, started, reason)
            if self._allowed_keys is not None and spec.key not in self._allowed_keys:
                return self._fail(request, ctx, started, f"expert {spec.key!r} not granted to this caller")

            # Structured invocation: the arguments must satisfy the expert's
            # input_schema — never free-form text.
            try:
                args = spec.input_schema(**request.arguments)
            except Exception as exc:
                return self._fail(request, ctx, started, f"bad arguments: {exc}")

            env = self._build_env(spec, ctx)
            async with self._workspace_transaction(env, ctx, spec.key):
                try:
                    # seed any uploaded input files into this expert's workspace before
                    # it runs (no-op unless it has a workspace and the run carried files).
                    # Bounded like the run itself: an archive can mean up to archive_max_
                    # entries sequential malware-scan round trips, with nothing else to
                    # stop a slow/unreachable scanner from hanging this call indefinitely.
                    try:
                        await asyncio.wait_for(
                            self._seed_inputs(env, ctx, spec.key),
                            timeout=settings.EXPERTS.timeout_s,
                        )
                    except asyncio.TimeoutError:
                        self._record_seed_fault(env, ctx)
                    except Exception as exc:  # noqa: BLE001 — a seed fault must degrade this
                        self._record_seed_fault(env, ctx, reason=f"input seeding failed: {exc}")
                    try:
                        output = await asyncio.wait_for(
                            spec.impl().run(args, env), timeout=settings.EXPERTS.timeout_s
                        )
                    except asyncio.TimeoutError:
                        return self._fail(request, ctx, started, "expert timed out")
                    except Exception as exc:
                        return self._fail(request, ctx, started, f"expert error: {exc}")

                    ref = uuid4().hex[:8]
                    # capture designated output artifacts out of the workspace BEFORE it
                    # is torn down (the finally below closes it)
                    artifacts = await self._capture_artifacts(output, env, ctx)
                    await self._index_code_symbols(env, ctx)
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
                    # Cross-call persistence: snapshot BEFORE the sandbox dies,
                    # success or fail. Keep close in its own finally so a snapshot
                    # cancellation/fault cannot leak the workspace or keyed lock.
                    if env.workspace is not None:
                        try:
                            await self._snapshot_mission_workspace(spec.key, env, ctx)
                        finally:
                            await env.workspace.close()

    @asynccontextmanager
    async def _workspace_transaction(self, env, ctx: VrakshaContext, expert_key: str):
        """Serialize restore → run → snapshot for one user's mission/expert only."""
        if env.workspace is None or not ctx.mission_id:
            yield
            return
        key = (ctx.user_id, ctx.mission_id, expert_key)
        async with _WORKSPACE_TRANSACTIONS.hold(key):
            yield

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
        # NETWORK-capable experts get NO memory push and NO need-context channel:
        # user memory sitting in the same prompt as an outbound channel (http/web) is
        # an exfiltration surface under prompt injection. Their user context arrives
        # solely through what the orchestrator brokers into the task prompt pre-spawn.
        networked = any(s.permission == PermissionLevel.NETWORK for s in granted)
        hydration = [] if networked else list(getattr(ctx, "hydration_items", None) or [])
        return ExpertEnv(
            module_dir=module_dir,
            model_role=spec.model_role,
            skills=skills,
            toolbox=self._toolbox_for(granted, ctx, workspace),
            granted=granted,
            findings=list(ctx.expert_findings),
            # the turn's hydrated memory, pushed to the (stateless) expert — the
            # Manager hydrated it once at loop start; think() folds it into the task
            hydration=hydration,
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

    async def _seed_inputs(self, env, ctx: VrakshaContext, expert_key: str) -> None:
        """Place the run's uploaded input files into this expert's workspace so it
        can read them with its file tools. No-op unless the expert actually has a
        workspace and the run carried files. Records the seeded names (+ any honest
        misses, with why) on the env so think() can tell the expert what's actually
        there — a silent gap here would leave the expert working from an empty
        workspace with no idea why. Best-effort per file — except an "archive"
        modality file, which is extracted member-by-member (see `_extract_archive`)
        rather than written as one opaque zip blob, and is all-or-nothing.

        Cross-call persistence restore runs FIRST, before any of that: if this
        mission (`ctx.mission_id`) has a workspace snapshot from an earlier call to
        THIS expert, and this call did NOT bring a fresh archive upload of its own,
        the snapshot is restored as the workspace's starting state. A fresh archive
        upload is an explicit "here's the (possibly new) repo" signal and always
        wins outright — no merge with a stale snapshot (see `_restore_mission_
        workspace`'s own docstring)."""
        files = list(getattr(ctx, "input_files", None) or [])
        if env.workspace is not None and ctx.mission_id and not any(f.modality == "archive" for f in files):
            await self._restore_mission_workspace(env.workspace, ctx, expert_key)
        if env.workspace is None or not files:
            return
        seeded: list[str] = []
        failures: list[tuple[str, str]] = []
        for f in files:
            if f.modality == "archive":
                names, reason = await self._extract_archive(env.workspace, f)
                if reason is not None:
                    failures.append((f.name, reason))
                    self._record_seed_failure(ctx, f.name, reason)
                seeded.extend(names)
                continue
            try:
                await env.workspace.write_bytes(f.name, f.data)
                seeded.append(f.name)
            except Exception as exc:  # noqa: BLE001 — one bad file must not sink the run
                reason = f"could not be written: {exc}"
                failures.append((f.name, reason))
                self._record_seed_failure(ctx, f.name, reason)
        env.input_files = seeded
        env.seed_failures = failures

    def _record_seed_failure(self, ctx: VrakshaContext, name: str, reason: str) -> None:
        """Audit an input file that seeded nothing — surfaced to the expert via
        `env.seed_failures` (see `_input_files_note`), and here for the trace/decision
        log too."""
        ctx.tool_calls.append(ToolCallRecord(
            tool_name="fs.seed_input", arguments={"name": name},
            result=None, success=False, duration_ms=0.0, error=reason,
        ))

    def _record_seed_fault(self, env, ctx: VrakshaContext, reason: str = "input seeding timed out") -> None:
        """`_seed_inputs` was cut short mid-run — by the outer timeout, or by ANY
        exception `_seed_inputs`/`_extract_archive` didn't already turn into a
        per-file failure (a `zipfile`/OS fault outside the caught `BadZipFile`
        case, say). Either way its own `env.input_files`/`seed_failures` writes
        never happened (a cancelled coroutine's local state is discarded; a raised
        exception unwinds past its own `env.input_files = seeded` line), so every
        requested upload is recorded as an honest miss here instead of either
        leaving env at its empty defaults with no explanation, or letting the
        fault propagate out of `_run_one` and take down every OTHER expert in the
        same `run_experts` gather (`asyncio.gather` with no `return_exceptions`).
        Whatever bytes an archive extraction had already written to the workspace
        before the fault may still be on disk (no delete primitive to undo it) —
        never claimed as seeded, same "visible, not silent" rule as every other
        failure path in this file."""
        names = [f.name for f in getattr(ctx, "input_files", None) or []]
        env.input_files = []
        env.seed_failures = [(name, reason) for name in names]
        for name in names:
            self._record_seed_failure(ctx, name, reason)

    async def _extract_archive(self, workspace, f) -> tuple[list[str], str | None]:
        """Extract an admitted zip `InputFile` into the workspace member-by-member —
        the CB2 real-repo-input track. All-or-nothing: any cap breach, unsafe member
        path, or malware hit rejects the WHOLE archive, nothing written (a silently
        partial repo is worse than a rejected upload) — returns `([], reason)`, never
        a partial name list, so a caller can never mistake a rejected archive for a
        seeded one. The ratio-based bomb-guard cap here is specific to an UPLOAD
        (bounded relative to what the user actually sent); `_restore_mission_
        workspace` shares this same validate-then-write shape for a workspace
        SNAPSHOT, which has no upload size to bound a ratio against, so it uses its
        own absolute cap instead (`_validate_archive_members`'s `total_cap` param)."""
        total_cap = settings.SECURITY.archive_max_uncompressed_ratio * max(len(f.data), 1)
        members, reason = await _validate_archive_members(f.data, total_cap)
        if reason is not None:
            return [], reason
        return await _write_members(workspace, members)

    async def _snapshot_mission_workspace(self, expert_key: str, env, ctx: VrakshaContext) -> None:
        """Cross-call persistence, the write side: zip this call's finished workspace
        and store it keyed on `(mission_id, expert_key)`, so THIS expert's next call
        within the SAME mission can pick up where this one left off (`_restore_
        mission_workspace`). No-op outside a mission (`ctx.mission_id == ""`, the
        only real value until missions are the caller) — zero behavior change to an
        ordinary one-shot chat turn. Best-effort: an oversized workspace skips its
        snapshot (never truncates one — a half-written zip would corrupt the NEXT
        restore), a store fault is recorded but never fails the run that just
        finished. `_run_one` holds the matching mission workspace transaction
        across restore, expert execution, and this snapshot."""
        if not ctx.mission_id:
            return
        data = await _snapshot_workspace(env.workspace)
        if data is None:
            ctx.tool_calls.append(ToolCallRecord(
                tool_name="fs.mission_snapshot", arguments={"expert": expert_key},
                result=None, success=False, duration_ms=0.0,
                error=f"workspace exceeded the {settings.SECURITY.max_workspace_snapshot_bytes}-byte "
                      "snapshot cap; persistence skipped this call",
            ))
            return
        try:
            await self._artifact_store().put(_mission_workspace_key(ctx.mission_id, expert_key), "_workspace.zip", data)
        except Exception as exc:  # noqa: BLE001 — persistence is best-effort, never fails a finished run
            ctx.tool_calls.append(ToolCallRecord(
                tool_name="fs.mission_snapshot", arguments={"expert": expert_key},
                result=None, success=False, duration_ms=0.0, error=str(exc)[:200],
            ))

    async def _restore_mission_workspace(self, workspace, ctx: VrakshaContext, expert_key: str) -> None:
        """Cross-call persistence, the read side: if this mission has a snapshot from
        an earlier call to THIS expert, restore it as the workspace's starting state
        before anything else seeds in. A missing snapshot (this mission's first call
        to this expert) is the expected, silent no-op case — `FileNotFoundError` is
        `LocalArtifactStore`'s own signal for that (see its `get()`), not a fault.
        Routes through the SAME validated-member path an upload uses
        (`_validate_archive_members`/`_write_members`) — including the malware
        re-scan per member: bytes this mission produced in an EARLIER turn could
        still carry the effects of an earlier prompt-injected upload, so "it's our
        own output" isn't a reason to skip the same gate an upload gets."""
        key = _mission_workspace_key(ctx.mission_id, expert_key)
        try:
            data = await self._artifact_store().get(f"{key}/_workspace.zip")
        except FileNotFoundError:
            return
        except Exception as exc:  # noqa: BLE001 — a store fault must not sink the run
            ctx.tool_calls.append(ToolCallRecord(
                tool_name="fs.mission_restore", arguments={"expert": expert_key},
                result=None, success=False, duration_ms=0.0, error=str(exc)[:200],
            ))
            return
        members, reason = await _validate_archive_members(data, settings.SECURITY.max_workspace_snapshot_bytes)
        if reason is not None:
            ctx.tool_calls.append(ToolCallRecord(
                tool_name="fs.mission_restore", arguments={"expert": expert_key},
                result=None, success=False, duration_ms=0.0, error=reason,
            ))
            return
        names, reason = await _write_members(workspace, members)
        if reason is not None:
            ctx.tool_calls.append(ToolCallRecord(
                tool_name="fs.mission_restore", arguments={"expert": expert_key},
                result=None, success=False, duration_ms=0.0, error=reason,
            ))
            return
        ctx.tool_calls.append(ToolCallRecord(
            tool_name="fs.mission_restore", arguments={"expert": expert_key},
            result={"files_restored": len(names)}, success=True, duration_ms=0.0,
        ))

    def _artifact_store(self):
        """Lazy `ArtifactStore` — shared by `_capture_artifacts` (output capture) and
        the mission-workspace snapshot/restore pair above."""
        if self._artifacts is None:
            from core.artifacts import LocalArtifactStore
            self._artifacts = LocalArtifactStore()
        return self._artifacts

    async def _index_code_symbols(self, env, ctx: VrakshaContext) -> None:
        """CB2 code-symbol tier (`code_symbols.index_code_symbols`) — server-side,
        automatic, never model-facing, same posture as `_capture_artifacts`/
        `_snapshot_mission_workspace`. Only fires when THIS `ExpertHandler` was
        explicitly given a `GraphPort` (`self._graph is not None` — an opt-in per
        `Capabilities.scoped_to()`'s `graph` param, see `batches.py`'s
        `grants_graph`; `.open()`'s central-tier handler always has one). Never a
        gate on the run that just finished — a fault here is recorded, not raised."""
        if self._graph is None or env.workspace is None:
            return
        entities, calls_edges, error = await code_symbols.index_code_symbols(self._graph, ctx, env.workspace)
        if error:
            ctx.tool_calls.append(ToolCallRecord(
                tool_name="graph.index_symbols", arguments={}, result=None,
                success=False, duration_ms=0.0, error=error,
            ))
        elif entities:
            ctx.tool_calls.append(ToolCallRecord(
                tool_name="graph.index_symbols", arguments={},
                result={"entities": entities, "calls_edges": calls_edges}, success=True, duration_ms=0.0,
            ))

    async def _capture_artifacts(self, output, env, ctx: VrakshaContext) -> list[dict]:
        """Copy the expert's designated output files out of the (about-to-be-closed)
        workspace into durable storage; return their references as dicts. Best-effort:
        a missing, oversized, or unreadable artifact is skipped, never fatal."""
        paths = list(getattr(output, "artifacts", None) or [])
        if not paths or env.workspace is None:
            return []
        store = self._artifact_store()
        refs: list[dict] = []
        for path in paths[:settings.EXPERTS.max_artifacts]:
            try:
                data = await env.workspace.read_bytes(path)
            except Exception:  # noqa: BLE001 — designated file missing/unreadable -> skip
                continue
            if len(data) > settings.EXPERTS.max_artifact_bytes:
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
