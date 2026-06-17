"""
Shared helpers for the per-modality sanitizer workers.

Each modality worker (text/pdf/image/audio/video) runs a small set of
independent sub-workers and then reduces their results. Two pieces of that
machinery are identical across modalities and live here so the logic exists
once:

* ``highest_threat`` — pick the most severe ThreatLevel a sub-worker reported.
* ``run_subworker`` — run one sub-worker and wrap unexpected failures in a
  SanitizationError carrying modality/worker context.

These are generalized over the per-worker result type via a Protocol: the
reducer only reads ``.threat_level``, and the runner only cares that the
sub-worker is a callable returning such a result. Behavior is preserved exactly
from the previous per-worker copies; the superset behavior (re-raise an existing
SanitizationError instead of double-wrapping it) is adopted for every modality.
"""

from typing import Callable, Protocol, TypeVar

from foundation import SanitizationError, ThreatLevel


class _HasThreatLevel(Protocol):
    """Minimal surface the reducer needs from a sub-worker result."""

    threat_level: ThreatLevel


# The reducer is read-only over results, so the result type is covariant.
ResultT = TypeVar("ResultT", bound=_HasThreatLevel, covariant=True)
# The runner's input payload type (str / bytes / Path) varies by modality.
PayloadT = TypeVar("PayloadT")


# Severity ordering for ThreatLevel, lowest to highest. Defined once here so the
# reducer is identical for every modality.
_THREAT_ORDER = {
    ThreatLevel.NONE: 0,
    ThreatLevel.LOW: 1,
    ThreatLevel.MEDIUM: 2,
    ThreatLevel.HIGH: 3,
    ThreatLevel.CRITICAL: 4,
}


def highest_threat(results: "list[_HasThreatLevel]") -> ThreatLevel:
    """Return the most severe threat level reported by sub-workers."""
    if not results:
        return ThreatLevel.NONE

    return max(
        (result.threat_level for result in results),
        key=_THREAT_ORDER.__getitem__,
    )


def run_subworker(
    worker: "Callable[[PayloadT], ResultT]",
    payload: "PayloadT",
    *,
    modality: str,
    label: str,
) -> "ResultT":
    """
    Run one sub-worker and wrap unexpected errors with sanitizer context.

    An existing SanitizationError is re-raised unchanged so its original
    modality/worker attribution is preserved (rather than being double-wrapped).
    Any other exception is wrapped with this modality's context, deriving the
    worker name from the sub-worker's function name.

    ``modality`` is the lowercase modality stored on the SanitizationError;
    ``label`` is the human-readable prefix used in the wrapped message (e.g.
    "Text", "PDF", "Audio", "Video").
    """
    try:
        return worker(payload)
    except SanitizationError:
        raise
    except Exception as exc:
        worker_name = worker.__name__.removeprefix("_").removesuffix("_worker")
        raise SanitizationError(
            f"{label} sanitizer worker failed: {exc}",
            modality=modality,
            worker=worker_name,
        ) from exc
