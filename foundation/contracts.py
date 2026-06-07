"""
Shared pipeline payload contracts.

These dataclasses describe the shape of payloads that travel through Flow. They
are not transport themselves; Flow remains the only runtime carrier between
stages. Keeping cross-stage schemas here avoids coupling one stage to another
stage's implementation module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .pillars.types import MemoryStore, ThreatLevel


@dataclass(slots=True)
class NormalizedInput:
    """
    Structured payload passed from normalizer to verifier/orchestrator.

    content is text when code-only normalization can produce text. native_payload
    is preserved when the target model supports that modality directly.
    requires_expert marks media that needs a capable model/tool later because
    normalizer itself stays code-only.
    """
    modality: str
    content_type: str
    content: str | None = None
    native_payload: Any | None = None
    target_layer: str = "orchestrator"
    target_provider: str | None = None
    target_model: str | None = None
    preserved_native: bool = False
    requires_expert: bool = False
    required_capability: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """
    Structured verifier output stored on flow.ctx.verifier_result.

    The verifier never produces user-facing prose. reason is internal context
    for logs, dead letters, and later safe orchestration decisions.
    """
    proceed: bool
    dangerous: bool = False
    warn: bool = False
    threat_level: ThreatLevel = ThreatLevel.NONE
    reason: str | None = None
    categories: list[str] = field(default_factory=list)
    routing_action: str = "direct"
    requires_expert: bool = False
    required_capability: str | None = None
    target_provider: str | None = None
    target_model: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Memory boundary contracts
# The orchestrator and the memory layer exchange these through the MemoryPort
# (foundation/ports.py). They live here, not inside either layer, so neither
# layer imports the other — both depend only on this shared shape.
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MemoryItem:
    """One retrieved memory, ready to hydrate into orchestrator context."""
    store: MemoryStore
    content: str
    score: float = 0.0          # per-query relevance
    trust: int = 0              # higher = more authoritative (wiki > inferred)


@dataclass(frozen=True, slots=True)
class HydrationRequest:
    """What the orchestrator asks the memory manager to hydrate for a turn."""
    session_id: str
    normalized: NormalizedInput | None = None
    token_budget: int = 0


@dataclass(slots=True)
class HydrationPackage:
    """
    The memory manager's reply: ranked, budget-bounded context to inject.
    The Phase-1 stub returns an empty package.
    """
    items: list[MemoryItem] = field(default_factory=list)
    token_budget: int = 0
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class MemoryWriteProposal:
    """
    A write the orchestrator/experts PROPOSE after a task. Nothing writes memory
    directly — the memory manager owns whether/where/how a proposal is persisted.
    """
    store: MemoryStore
    content: str
    rationale: str = ""
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Orchestrator output contract
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class OrchestratorResponse:
    """
    The orchestrator's draft answer, stored on ctx.orchestrator_response. This is
    the input to the (future) output filter, not the final user-facing text.
    """
    text: str
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    finding_refs: list[str] = field(default_factory=list)   # -> ctx.expert_findings
