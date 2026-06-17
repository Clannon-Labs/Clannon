"""
Single source of truth for classifying a provider/model failure.

Two stages used to answer "what KIND of failure is this?" independently and in
divergent idioms:

* the retry wrapper (``retry.py``) classified *structurally* — exception types
  and HTTP status codes — to decide whether a short backoff might clear it; and
* the orchestrator's graceful-degradation path (``utils/recovery.py``) re-classified
  the SAME exception trees by string-matching the message text, to pick the
  degraded-mode reason the user hears.

A new provider error shape had to be taught to both. This module unifies the
CLASSIFICATION (not the policy): it returns a single ``FailureKind`` that is the
union of everything both classifiers detected — structural type/status checks
PLUS the string fallbacks recovery had — so neither caller loses a case it used
to catch. Each caller keeps its own POLICY:

* ``retry.py`` asks :func:`is_transient` (kind in the transient set) for its
  retry decision; backoff behaviour is unchanged.
* ``recovery.py`` calls :func:`classify_failure` then maps the kind to its
  user-facing degraded reason; the reasons are unchanged.

Import direction: ``core.orchestrator`` may import from ``core.llm`` (it already
does). ``core.llm`` must NOT import from ``core.orchestrator``.
"""

from __future__ import annotations

import asyncio
from typing import Literal

import httpx
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError

# The union of what both original classifiers distinguished:
#   rate_limit   — a provider quota / 429 / "at capacity" condition
#   timeout      — the run ran out of wall-clock time
#   server_error — a transient 5xx / 408 / transport / connection failure that a
#                  short backoff might clear, but is NOT specifically a rate limit
#   error        — anything else (permanent: bad request, auth, missing model, bug)
#
# retry cares about {rate_limit, timeout, server_error} == transient.
# recovery cares about the user-facing distinction and collapses server_error
# into "error" (see the mapping in utils/recovery.py) to keep its existing
# three-value, user-facing output identical.
FailureKind = Literal["rate_limit", "timeout", "server_error", "error"]

# Rate limiting plus transient server/gateway failures. Permanent 4xx codes
# (400/401/403/404 — bad request, auth, missing model) are deliberately excluded:
# retrying them only wastes time and hides the real fault.
_RATE_LIMIT_STATUS = frozenset({429})
_TRANSIENT_STATUS = frozenset({408, 429, 500, 502, 503, 504})

# Message markers that identify a provider rate-limit / quota-exhaustion anywhere
# in the raised exception tree (FallbackExceptionGroup wraps one per model+key).
# These are the string fallbacks recovery.py relied on, kept verbatim so the
# superset still catches every provider phrasing the old code did.
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


def _looks_rate_limited(exc: BaseException, seen: set[int]) -> bool:
    """True if a rate-limit signal appears in this exception, its sub-exceptions
    (ExceptionGroup / FallbackExceptionGroup), or its cause/context chain.

    This is the superset of both old detections: the structural ``status_code ==
    429`` / ``ModelHTTPError(429)`` check AND the string markers recovery used.
    The ``seen`` set guards against cyclic ``__cause__`` chains."""
    if id(exc) in seen:                      # guard against cyclic __cause__ chains
        return False
    seen.add(id(exc))
    if isinstance(exc, ModelHTTPError) and exc.status_code in _RATE_LIMIT_STATUS:
        return True
    blob = f"{type(exc).__name__} {exc}".lower()
    if getattr(exc, "status_code", None) == 429 or any(m in blob for m in _RATE_LIMIT_MARKERS):
        return True
    for sub in getattr(exc, "exceptions", ()) or ():     # ExceptionGroup members
        if _looks_rate_limited(sub, seen):
            return True
    cause = exc.__cause__ or exc.__context__
    return _looks_rate_limited(cause, seen) if cause is not None else False


def classify_failure(exc: BaseException) -> FailureKind:
    """Classify a provider/model failure into a single canonical kind.

    Precedence is deliberate and preserves recovery's original ordering:
    rate-limit wins over timeout (a stalled run is most often a 429 storm retried
    into the wall clock), and only then the transient-server / timeout / permanent
    buckets. The rate-limit walk recurses through ExceptionGroup members and the
    cause/context chain; the rest inspect the outermost exception."""
    if _looks_rate_limited(exc, set()):
        return "rate_limit"
    if isinstance(exc, TimeoutError):        # asyncio.TimeoutError is an alias since 3.11
        return "timeout"
    if _is_transient_server(exc):
        return "server_error"
    return "error"


def _is_transient_server(exc: BaseException) -> bool:
    """True for non-rate-limit, non-timeout transient faults a short backoff might
    clear: transient 5xx/408, a non-HTTP ModelAPIError (transport/connection), or
    an httpx transport error. Inspects the outermost exception only — group
    handling for the retry decision lives in :func:`is_transient`."""
    if isinstance(exc, ModelHTTPError):
        return exc.status_code in _TRANSIENT_STATUS
    # A ModelAPIError that is not an HTTP error is a transport/connection
    # failure (no status code) — treat as transient and retry.
    if isinstance(exc, ModelAPIError):
        return True
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError, asyncio.TimeoutError)):
        return True
    return False


def is_transient(exc: BaseException) -> bool:
    """True for provider failures that a short backoff might clear — the retry
    wrapper's decision. Preserves the original ``_is_transient`` semantics exactly:

    * A FallbackModel that exhausts its chain raises an ExceptionGroup of the
      per-model failures. If ANY member is transient (a rate-limit window, a
      congestion spike), waiting and re-running the whole chain can succeed.
    * Otherwise a failure is transient iff its kind is rate_limit, timeout, or a
      transient server/transport error.
    """
    if isinstance(exc, BaseExceptionGroup):
        return any(is_transient(sub) for sub in exc.exceptions)
    return classify_failure(exc) in ("rate_limit", "timeout", "server_error")
