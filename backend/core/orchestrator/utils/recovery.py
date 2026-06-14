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

from foundation import OrchestratorResponse, VrakshaContext

FailureKind = Literal["rate_limit", "timeout", "error"]

# markers that identify a provider rate-limit / quota-exhaustion anywhere in the
# raised exception tree (FallbackExceptionGroup wraps one per model+key)
_RATE_LIMIT_MARKERS = (
    "429",
    "resource_exhausted",
    "rate limit",
    "ratelimit",
    "quota",
    "exceeded your current quota",
    "usage limits",
    "overloaded",
    "too many requests",
)

# how much of each partial finding to surface, and how many, so a degraded
# answer stays legible (and well under the filter's input bounds)
_PER_FINDING_CHARS = 4000
_MAX_FINDINGS = 6


def _markers_in(exc: BaseException, seen: set[int]) -> bool:
    """True if any rate-limit marker appears in this exception, its cause, or its
    sub-exceptions (ExceptionGroup / FallbackExceptionGroup)."""
    if id(exc) in seen:                      # guard against cyclic __cause__ chains
        return False
    seen.add(id(exc))
    blob = f"{type(exc).__name__} {exc}".lower()
    if getattr(exc, "status_code", None) == 429 or any(m in blob for m in _RATE_LIMIT_MARKERS):
        return True
    for sub in getattr(exc, "exceptions", ()) or ():     # ExceptionGroup members
        if _markers_in(sub, seen):
            return True
    cause = exc.__cause__ or exc.__context__
    return _markers_in(cause, seen) if cause is not None else False


def classify_failure(exc: BaseException) -> FailureKind:
    """Map a loop failure to the cause the user should hear about. Rate-limit wins
    over timeout: a stalled run is most often a 429 storm retried into the wall clock."""
    if _markers_in(exc, set()):
        return "rate_limit"
    if isinstance(exc, TimeoutError):        # asyncio.TimeoutError is an alias since 3.11
        return "timeout"
    return "error"


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
    usable = [f for f in findings if getattr(f, "full_content", "")][:_MAX_FINDINGS]
    if usable:
        parts.append("\n\nHere is what was gathered before the run stopped:")
        for f in usable:
            body = f.full_content.strip()[:_PER_FINDING_CHARS]
            parts.append(f"\n\n### {_humanize(f.expert)}\n{body}")
    return OrchestratorResponse(
        text="".join(parts),
        confidence=0.1,
        metadata={"degraded": True, "cause": kind},
        finding_refs=[f.ref for f in usable],
    )
