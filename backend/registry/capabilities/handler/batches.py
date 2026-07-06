"""
Generic batch handler — the batch orchestrator, one tier above ExpertHandler
(batch-orchestrator design v2, `proposals/archive/to-backend/
2026-07-06_batch-orchestrator-design-v2.md` §B3). A "batch" is the existing
orchestrator loop, scoped to one domain's experts/tools via
`Capabilities.scoped_to()` — same guarded gateway, same two-output split, one
level up. `spawn_batch(batch_key, task)` is the CENTRAL orchestrator's one new
native tool (unlike experts, there is no per-batch wrapper).

RECURSION GUARD (structural, not a runtime check): `Capabilities.scoped_to()`
never accepts a `batch_registry` — only `Capabilities.open()` does. So a
batch's own scoped `Capabilities` always has `_batches=None` and never offers
`spawn_batch` to its own model. A batch cannot spawn a batch.

Batch membership (`batch_key` -> its expert/tool key set) is NOT built here —
`BatchHandler` starts with an empty registry until backend places
`config/backend/batches.yaml` (ratified, not yet built: no concrete batch has
been proposed yet, per the design's §H decomposition discipline). It takes the
registry as a plain `dict[str, BatchDefinition]` injected at construction —
the mechanism is complete and tested today; it starts inert (no batch_key
resolves to anything) until a real entry exists, at which point `spawn_batch`
appears on the model's tool list automatically (see `support.
build_orchestrator_tools`'s non-empty-registry gate) with no further code
change here.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from uuid import uuid4

from foundation import BatchAwarenessPort, BatchLifecycleStatus, CrossBatchAwareness, PermissionLevel, VrakshaContext

from .. import registry as default_registry
from ..schemas import BatchFindings, BatchSummary

# Tree-local for now (registry/capabilities is my tree; foundation.constants is
# backend's seam) -- candidate for promotion to foundation.vocab.constants once
# a concrete batch exists and this needs central tuning like EXPERT_MAX_CONCURRENT.
_BATCH_MAX_CONCURRENT = 2          # batches run heavier sub-turns than a single expert
_BATCH_TIMEOUT_S = 600.0          # a batch may itself run several experts sequentially
_BATCH_SUMMARY_MAX_CHARS = 500    # bounded excerpt returned to the central model
_AWARENESS_HEADLINE_MAX_CHARS = 200   # matches BatchAwarenessItem's "single-line gist" contract


@dataclass(frozen=True, slots=True)
class BatchDefinition:
    """One batch's scope -- what `Capabilities.scoped_to()` is built from. The
    plain-mapping shape `config/backend/batches.yaml` will eventually load into
    (backend's seam); constructed directly here and in tests until then."""
    domain: str   # the batch's stable identity for cross-batch awareness (e.g. "engineering");
                  # distinct from the per-invocation batch_id spawn_batch mints (b1-item-3 design, §2/§3)
    expert_keys: frozenset[str]
    tool_keys: frozenset[str]
    grants: frozenset[PermissionLevel] = frozenset({PermissionLevel.READ})
    allow_memory_write: bool = False   # ratified default-excludes-remember posture (design v2 §C)
    system_prompt: str = (
        "You are a scoped batch orchestrator working one sub-task of a larger mission. "
        "Use only the experts/tools you have been granted. Answer only the task given to you."
    )


def _with_awareness_context(task: str, awareness: CrossBatchAwareness) -> str:
    """Folds a bounded cross-batch awareness read into this batch's own task
    prompt -- internal to its scoped turn, never surfaced to the central
    orchestrator's own context (the two-output split still holds one tier up).
    A degraded or empty read changes nothing, so a batch behaves identically
    to today whenever awareness has nothing to say (b1-item-3 design §5)."""
    if awareness.degraded or not awareness.items:
        return task
    lines = [f"- {item.domain} ({item.status.value}): {item.headline}" for item in awareness.items]
    section = "Other batches currently active in this mission:\n" + "\n".join(lines)
    if awareness.notes:
        section += f"\n({awareness.notes})"
    return f"{task}\n\n---\n{section}"


class BatchHandler:
    """Implements the batch tier over the capability registry -- mirrors
    ExpertHandler one level up."""

    def __init__(
        self, batch_registry: dict[str, BatchDefinition] | None = None, registry=default_registry,
        awareness: BatchAwarenessPort | None = None,
    ) -> None:
        self._batch_registry = dict(batch_registry or {})
        self._registry = registry   # the CapabilityRegistry to open scoped Capabilities against
        self._awareness = awareness   # None until wiring.py threads a real BatchAwarenessPort (b1-item-3)
        self._semaphore = asyncio.Semaphore(_BATCH_MAX_CONCURRENT)

    @property
    def has_batches(self) -> bool:
        """Whether any batch is actually configured -- gates whether `spawn_batch`
        is offered to the model at all (an always-refusing tool is dead surface,
        not a working one)."""
        return bool(self._batch_registry)

    async def spawn_batch(self, batch_key: str, task: str, ctx: VrakshaContext, *, model=None) -> BatchSummary:
        async with self._semaphore:
            started = time.monotonic()
            definition = self._batch_registry.get(batch_key)
            if definition is None:
                return await self._fail(batch_key, None, task, ctx, started, f"batch {batch_key!r} not configured")

            # Per-invocation, not per-domain (b1-item-3 design §2): two concurrent
            # same-domain batches must not clobber one status row -- domain=batch_key
            # is the stable display identity, batch_id is unique per spawn_batch call.
            batch_id = uuid4().hex[:8]

            if self._awareness is not None:
                await self._awareness.record_batch_status(
                    ctx.user_id, ctx.mission_id, batch_id, definition.domain,
                    BatchLifecycleStatus.ACTIVE, headline=task[:_AWARENESS_HEADLINE_MAX_CHARS],
                )
                awareness = await self._awareness.cross_batch_awareness(ctx.user_id, ctx.mission_id, batch_id)
                task = _with_awareness_context(task, awareness)

            from .capability import Capabilities   # deferred: capability.py imports this module at top level

            scoped = Capabilities.scoped_to(
                ctx,
                expert_keys=definition.expert_keys,
                tool_keys=definition.tool_keys,
                grants=definition.grants,
                allow_memory_write=definition.allow_memory_write,
                registry=self._registry,
            )

            from core.orchestrator.schemas import OrchestratorAnswer

            try:
                # No on_event/on_message sinks: a batch's own decision log/chat
                # voice stays internal -- the central orchestrator's live stream
                # only ever shows its own turns, never a batch's internals.
                answer = await asyncio.wait_for(
                    scoped.run_turn(
                        system_prompt=definition.system_prompt,
                        user_prompt=task,
                        output_type=OrchestratorAnswer,
                        model=model,
                    ),
                    timeout=_BATCH_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                return await self._fail(batch_key, batch_id, task, ctx, started, "batch timed out", definition=definition)
            except Exception as exc:  # noqa: BLE001 -- a batch fault must not sink the mission
                return await self._fail(
                    batch_key, batch_id, task, ctx, started, f"batch error: {exc}", definition=definition,
                )

            ref = uuid4().hex[:8]
            ctx.batch_findings.append(
                BatchFindings(
                    batch=batch_key, ref=ref, full_content=answer.answer_text,
                    metadata={
                        "confidence": answer.confidence, "task": task,
                        "duration_ms": round((time.monotonic() - started) * 1000, 2),
                    },
                )
            )
            excerpt = answer.answer_text[:_BATCH_SUMMARY_MAX_CHARS]
            if self._awareness is not None:
                await self._awareness.record_batch_status(
                    ctx.user_id, ctx.mission_id, batch_id, definition.domain,
                    BatchLifecycleStatus.DONE, headline=excerpt[:_AWARENESS_HEADLINE_MAX_CHARS],
                )
            return BatchSummary(batch=batch_key, summary=excerpt, confidence=answer.confidence, finding_ref=ref)

    async def _fail(
        self, batch_key: str, batch_id: str | None, task: str, ctx: VrakshaContext, started: float, reason: str,
        *, definition: BatchDefinition | None = None,
    ) -> BatchSummary:
        # NOT recorded on ctx.expert_calls/ctx.tool_calls -- those are consumed by
        # api/'s expert-state reconciliation and CB4's decision-record derivation,
        # neither of which knows about the batch tier yet. A `ctx.batch_findings`-
        # only failure (no finding_ref) is visible to whatever reads that list;
        # broader batch-call audit visibility (CB4 participants, api/ UI state) is
        # a real, non-blocking foundation-seam gap, flagged to backend rather than
        # worked around by misusing an unrelated list.
        #
        # A crashed/timed-out batch still gets a FAILED record (b1-item-3 design §5):
        # otherwise it silently vanishes from cross_batch_awareness, reading as
        # "never existed" to its siblings rather than "failed" -- exactly the quiet-
        # failure case the awareness slice exists to surface. Only reachable when the
        # batch got far enough to mint a batch_id + resolve its definition; the
        # "not configured" path has neither, so there is nothing to record against.
        if self._awareness is not None and batch_id is not None and definition is not None:
            await self._awareness.record_batch_status(
                ctx.user_id, ctx.mission_id, batch_id, definition.domain,
                BatchLifecycleStatus.FAILED, headline=reason[:_AWARENESS_HEADLINE_MAX_CHARS],
            )
        return BatchSummary(batch=batch_key, summary=f"[unavailable] {reason}", confidence=0.0, finding_ref="")
