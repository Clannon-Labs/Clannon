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

import httpx
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError

from foundation import constants


# Rate limiting plus transient server/gateway failures. Permanent 4xx codes
# (400/401/403/404 — bad request, auth, missing model) are deliberately excluded:
# retrying them only wastes time and hides the real fault.
_TRANSIENT_STATUS = frozenset({408, 429, 500, 502, 503, 504})


def _is_transient(exc: BaseException) -> bool:
    """True for provider failures that a short backoff might clear."""
    if isinstance(exc, ModelHTTPError):
        return exc.status_code in _TRANSIENT_STATUS
    # A ModelAPIError that is not an HTTP error is a transport/connection
    # failure (no status code) — treat as transient and retry.
    if isinstance(exc, ModelAPIError):
        return True
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError, asyncio.TimeoutError)):
        return True
    return False


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

    for attempt in range(attempts):
        try:
            return await agent.run(*args, **kwargs)
        except Exception as exc:
            is_last = attempt == attempts - 1
            if is_last or not _is_transient(exc):
                raise
            await asyncio.sleep(min(delay, constants.LLM_RETRY_MAX_DELAY_S))
            delay *= 2
