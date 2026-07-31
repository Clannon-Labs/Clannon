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
from typing import Any, Iterator, NamedTuple


@dataclass
class Usage:
    """Token usage accumulated across every model call in one run.

    The four token counters are DISJOINT, because the provider reports them that
    way: `input_tokens` is the prefix that was billed at full rate, while the
    cached prefix is reported separately as a write (first call, ~1.25x) or a read
    (subsequent calls inside the cache window, ~0.1x). Summing them would be
    wrong for cost and double-counting for volume, so they stay apart and callers
    pick the one that answers their question.
    """
    input_tokens: int = 0
    output_tokens: int = 0
    # Prompt-cache counters. Every layer sets `anthropic_cache_instructions` /
    # `anthropic_cache_tool_definitions` (see `registry.model_settings_for_layer`),
    # but until these were carried through, NOTHING could observe whether the cache
    # actually HIT — the settings prove configuration, not effectiveness. A run with
    # a large `cache_read_tokens` is a cache that is working; one that only ever
    # writes is a prefix that changes between calls and is paying 1.25x for nothing.
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    requests: int = 0

    @property
    def total_tokens(self) -> int:
        """Tokens billed at the FULL input/output rate.

        Deliberately excludes the cache counters: this feeds `run.tokens_used` and
        the `/usage` meter, and changing what counts against a user's plan is a
        pricing decision, not a refactor. Use `total_tokens_processed` when the
        question is volume rather than spend.
        """
        return self.input_tokens + self.output_tokens

    @property
    def total_tokens_processed(self) -> int:
        """Every token the model actually read or wrote, cached or not."""
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )


_USAGE: ContextVar[Usage | None] = ContextVar("vraksha_usage", default=None)


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class RequestTokens(NamedTuple):
    """One model call's provider-reported counters.

    A NamedTuple so the two existing unpacking call sites keep working positionally
    while the cache counters ride along behind them (LAW 1: one unwrapper, not two).
    """
    input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


def extract_usage(result: Any) -> RequestTokens:
    """Pull the provider-reported token counters out of a pydantic-ai run result.

    `result.usage` carries the REAL provider-reported token counts. pydantic-ai >= 1.x
    exposes it as a PROPERTY (a RunUsage); older versions exposed it as a method. Only
    call it when it is a bare callable that is not already a usage object, so we read
    the true counts without tripping the deprecation warning. Best-effort: a shape we
    don't recognise returns zeros rather than raising — never let metering interfere
    with the run. Shared by `accumulate` (the usage_scope meter) and the budget
    anchor's reconcile (`core/llm/retry.py`), so there is exactly one unwrapper.

    `RunUsage` reports the cached prefix SEPARATELY from `input_tokens`
    (pydantic-ai maps Anthropic's `cache_creation_input_tokens` /
    `cache_read_input_tokens` onto `cache_write_tokens` / `cache_read_tokens`).
    Reading only `input_tokens` — which is what this did until 2026-07-31 — silently
    discarded both, which is why nothing could tell whether prompt caching was
    actually hitting."""
    try:
        usage = getattr(result, "usage", None)
        if callable(usage) and not hasattr(usage, "input_tokens"):
            usage = usage()
        if usage is None:
            return RequestTokens()
        return RequestTokens(
            _as_int(getattr(usage, "input_tokens", None)),
            _as_int(getattr(usage, "output_tokens", None)),
            _as_int(getattr(usage, "requests", None)),
            _as_int(getattr(usage, "cache_read_tokens", None)),
            _as_int(getattr(usage, "cache_write_tokens", None)),
        )
    except Exception:  # noqa: BLE001 — never let metering interfere with the run
        return RequestTokens()


def accumulate(result: Any) -> None:
    """Add one model run's usage to the active scope, if any. A no-op outside an
    active `usage_scope()` (e.g. the CLI, which does not meter)."""
    acc = _USAGE.get()
    if acc is None:
        return
    tokens = extract_usage(result)
    acc.input_tokens += tokens.input_tokens
    acc.output_tokens += tokens.output_tokens
    acc.requests += tokens.requests
    acc.cache_read_tokens += tokens.cache_read_tokens
    acc.cache_write_tokens += tokens.cache_write_tokens


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
