"""
Transient-error retry for model calls, shared by every LLM-using stage.

PydanticAI's ``Agent(retries=...)`` only re-runs on malformed *output*. It does
not retry transient *provider* failures (HTTP 429/5xx, connection drops,
timeouts), so a momentary demand spike (e.g. Gemini ``503 UNAVAILABLE``) turns a
legitimate request into a hard error. This wrapper adds bounded
exponential-backoff retries around an agent run for exactly those transient
cases, and re-raises everything else (bad key, other 4xx, usage-limit, malformed
output) immediately so real faults still surface fast.

Security note: retries are bounded by ``LLM_TRANSIENT_MAX_RETRIES``. When the
budget is exhausted the original error is re-raised, so a security stage built on
this (e.g. the verifier) still fails closed.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic_ai import Agent

from foundation import constants

from .failures import is_transient as _is_transient


async def run_agent(agent: Agent[Any, Any], *args: Any, **kwargs: Any) -> Any:
    """
    Run ``agent.run(*args, **kwargs)``, retrying only on transient provider errors.

    Backoff is exponential: ``LLM_RETRY_BASE_DELAY_S``, doubling each attempt,
    capped at ``LLM_RETRY_MAX_DELAY_S``, over ``LLM_TRANSIENT_MAX_RETRIES`` extra
    attempts. Any non-transient error raises immediately; an exhausted budget
    re-raises the last transient error so the caller fails closed.
    """
    attempts = constants.LLM_TRANSIENT_MAX_RETRIES + 1
    delay = constants.LLM_RETRY_BASE_DELAY_S
    # A FallbackModel that exhausts its chain already tried EVERY provider this round.
    # Re-running the whole chain on the full retry budget multiplies latency by the chain
    # length (N providers per attempt) for little gain — if every provider is rate-limited
    # now, a few seconds of backoff won't clear it. So cap whole-chain re-runs hard and let
    # the run fail fast into graceful degradation instead of spinning to the expert timeout.
    chain_retries_left = constants.LLM_FALLBACK_MAX_RETRIES

    for attempt in range(attempts):
        try:
            return await agent.run(*args, **kwargs)
        except Exception as exc:
            is_last = attempt == attempts - 1
            if is_last or not _is_transient(exc):
                raise
            if isinstance(exc, BaseExceptionGroup):     # the whole fallback chain exhausted
                if chain_retries_left <= 0:
                    raise
                chain_retries_left -= 1
            await asyncio.sleep(min(delay, constants.LLM_RETRY_MAX_DELAY_S))
            delay *= 2
