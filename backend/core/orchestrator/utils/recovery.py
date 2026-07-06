"""
Graceful degradation for the orchestrator stage.

When the reasoning loop cannot finish — a wall-clock timeout, a provider
rate-limit storm (every model in the fallback chain returning 429), or an
unexpected fault — the stage must NOT hand the user a blank failure. Instead it
returns an honest, legible answer assembled from whatever the run already
gathered. This path is deliberately LLM-FREE: when providers are rate-limited,
another model call would only fail again, so the degraded answer is built purely
from `ctx` state (the partial expert findings already buffered for the filter).

The result still flows through the output filter → delivery like any answer, so
the user sees real, grounded partial findings plus a clear note about what
happened, never nothing.
"""

from __future__ import annotations

from typing import Literal

import settings
from core.llm import classify_failure as _classify_llm_failure
from foundation import OrchestratorResponse, VrakshaContext

# The user-facing degraded reasons the orchestrator can surface. Classification
# (what KIND of failure this is) now lives in core/llm/failures.py — the single
# source of truth shared with the retry wrapper. recovery keeps only the POLICY:
# mapping a kind to its user-facing reason and building the degraded answer.
FailureKind = Literal["rate_limit", "timeout", "error"]


def classify_failure(exc: BaseException) -> FailureKind:
    """Map a loop failure to the cause the user should hear about.

    Delegates the actual classification to the shared core/llm classifier, then
    collapses its richer kinds into the three reasons the user sees: a transient
    non-rate-limit server/transport fault ("server_error") reads to the user as a
    generic error, exactly as the old string-only classifier rendered it.
    Rate-limit still wins over timeout (a stalled run is most often a 429 storm
    retried into the wall clock) — that precedence is enforced in the shared
    classifier."""
    kind = _classify_llm_failure(exc)
    if kind == "rate_limit":
        return "rate_limit"
    if kind == "timeout":
        return "timeout"
    return "error"          # "server_error" and "error" both surface as a generic error


_REASONS: dict[FailureKind, str] = {
    "rate_limit": (
        "This run couldn't finish because the AI providers are momentarily at capacity "
        "(rate-limited). This is temporary — please try again in a minute."
    ),
    "timeout": (
        "This run couldn't finish in the time allowed. This is usually transient (often "
        "provider rate limits under load) — please try again."
    ),
    "error": (
        "This run stopped early due to an unexpected error. Please try again; if it keeps "
        "happening, simplify the request."
    ),
}


def degraded_reason(kind: FailureKind) -> str:
    """The one-line honest explanation for this failure kind."""
    return _REASONS[kind]


def _humanize(expert_key: str) -> str:
    """`web.research` -> `Web research` for a readable section heading."""
    return expert_key.replace(".", " ").replace("_", " ").strip().capitalize()


def build_degraded_response(ctx: VrakshaContext, kind: FailureKind) -> OrchestratorResponse:
    """Build an honest, grounded answer from partial run state — no LLM call.

    Leads with the reason, then appends whatever expert findings were already
    gathered (so the user still gets value), each clearly attributed. With no
    findings, the reason alone is the answer — still better than a blank failure.
    """
    parts = [degraded_reason(kind)]
    findings = list(getattr(ctx, "expert_findings", []) or [])
    usable = [f for f in findings if getattr(f, "full_content", "")][:settings.ORCHESTRATOR.degraded_max_findings]
    if usable:
        parts.append("\n\nHere is what was gathered before the run stopped:")
        for f in usable:
            body = f.full_content.strip()[:settings.ORCHESTRATOR.degraded_per_finding_chars]
            parts.append(f"\n\n### {_humanize(f.expert)}\n{body}")
    return OrchestratorResponse(
        text="".join(parts),
        confidence=settings.ORCHESTRATOR.degraded_confidence,
        metadata={"degraded": True, "cause": kind},
        finding_refs=[f.ref for f in usable],
    )
