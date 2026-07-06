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

from foundation import PermissionLevel, VrakshaContext

from .. import registry as default_registry
from ..schemas import BatchFindings, BatchSummary

# Tree-local for now (registry/capabilities is my tree; foundation.constants is
# backend's seam) -- candidate for promotion to foundation.vocab.constants once
# a concrete batch exists and this needs central tuning like EXPERT_MAX_CONCURRENT.
_BATCH_MAX_CONCURRENT = 2          # batches run heavier sub-turns than a single expert
_BATCH_TIMEOUT_S = 600.0          # a batch may itself run several experts sequentially
_BATCH_SUMMARY_MAX_CHARS = 500    # bounded excerpt returned to the central model


@dataclass(frozen=True, slots=True)
class BatchDefinition:
    """One batch's scope -- what `Capabilities.scoped_to()` is built from. The
    plain-mapping shape `config/backend/batches.yaml` will eventually load into
    (backend's seam); constructed directly here and in tests until then."""
    expert_keys: frozenset[str]
    tool_keys: frozenset[str]
    grants: frozenset[PermissionLevel] = frozenset({PermissionLevel.READ})
    allow_memory_write: bool = False   # ratified default-excludes-remember posture (design v2 §C)
    system_prompt: str = (
        "You are a scoped batch orchestrator working one sub-task of a larger mission. "
        "Use only the experts/tools you have been granted. Answer only the task given to you."
    )


class BatchHandler:
    """Implements the batch tier over the capability registry -- mirrors
    ExpertHandler one level up."""

    def __init__(self, batch_registry: dict[str, BatchDefinition] | None = None, registry=default_registry) -> None:
        self._batch_registry = dict(batch_registry or {})
        self._registry = registry   # the CapabilityRegistry to open scoped Capabilities against
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
                return self._fail(batch_key, task, ctx, started, f"batch {batch_key!r} not configured")

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
                return self._fail(batch_key, task, ctx, started, "batch timed out")
            except Exception as exc:  # noqa: BLE001 -- a batch fault must not sink the mission
                return self._fail(batch_key, task, ctx, started, f"batch error: {exc}")

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
            return BatchSummary(batch=batch_key, summary=excerpt, confidence=answer.confidence, finding_ref=ref)

    def _fail(self, batch_key: str, task: str, ctx: VrakshaContext, started: float, reason: str) -> BatchSummary:
        # NOT recorded on ctx.expert_calls/ctx.tool_calls -- those are consumed by
        # api/'s expert-state reconciliation and CB4's decision-record derivation,
        # neither of which knows about the batch tier yet. A `ctx.batch_findings`-
        # only failure (no finding_ref) is visible to whatever reads that list;
        # broader batch-call audit visibility (CB4 participants, api/ UI state) is
        # a real, non-blocking foundation-seam gap, flagged to backend rather than
        # worked around by misusing an unrelated list.
        return BatchSummary(batch=batch_key, summary=f"[unavailable] {reason}", confidence=0.0, finding_ref="")
