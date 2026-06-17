"""
Per-run token usage accounting.

Every LLM call in a turn funnels through `retry.run_agent`, so that is the single
place token usage is captured. Within an active `usage_scope()` the tokens from each
model run are added to a per-run accumulator; outside a scope (e.g. the CLI, which
does not meter) accumulation is a no-op, so this carries zero overhead by default.

The accumulator is held in a ContextVar, scoped to one asyncio task tree, so
concurrent runs by different users never mix their counts. Callers wrap a run in
`with usage_scope() as usage:` and read `usage.total_tokens` afterwards — the LLM
boundary stays free of Flow/ctx, exactly like `model_overrides`.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator


@dataclass
class Usage:
    """Token usage accumulated across every model call in one run."""
    input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


_USAGE: ContextVar[Usage | None] = ContextVar("vraksha_usage", default=None)


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def accumulate(result: Any) -> None:
    """Add one model run's usage to the active scope, if any. Best-effort: a usage
    shape we don't recognise (or no active scope) is silently ignored — token
    accounting must never break a run."""
    acc = _USAGE.get()
    if acc is None:
        return
    try:
        # `result.usage` carries the REAL provider-reported token counts. pydantic-ai
        # >= 1.x exposes it as a PROPERTY (a RunUsage); older versions exposed it as a
        # method. Only call it when it is a bare callable that is not already a usage
        # object, so we read the true counts without tripping the deprecation warning.
        usage = getattr(result, "usage", None)
        if callable(usage) and not hasattr(usage, "input_tokens"):
            usage = usage()
        if usage is None:
            return
        acc.input_tokens += _as_int(getattr(usage, "input_tokens", None))
        acc.output_tokens += _as_int(getattr(usage, "output_tokens", None))
        acc.requests += _as_int(getattr(usage, "requests", None))
    except Exception:  # noqa: BLE001 — never let metering interfere with the run
        return


@contextmanager
def usage_scope() -> Iterator[Usage]:
    """Accumulate token usage for the duration of a run. Yields the live accumulator;
    read `.total_tokens` after the run completes."""
    acc = Usage()
    token = _USAGE.set(acc)
    try:
        yield acc
    finally:
        _USAGE.reset(token)
