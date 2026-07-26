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

This is also the money-enforcement anchor (``docs/architecture/
BUDGET_ENFORCEMENT_ANCHOR.md``): the ONLY place ``agent.run`` is called (invariant
gate in ``scripts/check_invariants.py``), so it is the single choke point every
LLM stage funnels through. Behind ``settings.BUDGET.enforcement_enabled`` (OFF by
default — inert, zero behavior change), it reserves an estimated µ$ cost before
the retry loop and reconciles the real cost after, refunding in full on any
non-success exit.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from pydantic_ai import Agent

from core.budget import context as budget_context
from core.budget.cost import ModelCall, call_cost_micros
from foundation import constants
import settings

from . import usage
from .failures import is_transient as _is_transient

log = logging.getLogger(__name__)


async def run_agent(
    agent: Agent[Any, Any],
    *args: Any,
    budget_model_id: str = "",
    budget_mission_id: str = "",
    budget_estimate_micros: int = 0,
    **kwargs: Any,
) -> Any:
    """
    Run ``agent.run(*args, **kwargs)``, retrying only on transient provider errors.

    Backoff is exponential: ``LLM_RETRY_BASE_DELAY_S``, doubling each attempt,
    capped at ``LLM_RETRY_MAX_DELAY_S``, over ``LLM_TRANSIENT_MAX_RETRIES`` extra
    attempts. Any non-transient error raises immediately; an exhausted budget
    re-raises the last transient error so the caller fails closed.

    ``budget_model_id``/``budget_mission_id``/``budget_estimate_micros`` are
    built by ``core/llm/framework.py`` (the one place both the layer's pricing
    model and the live ``deps.ctx.mission_id`` are in scope) and consumed ONLY
    here — never forwarded to ``agent.run``.
    """
    attempts = settings.LLM.transient_max_retries + 1
    delay = settings.LLM.retry_base_delay_s
    # A FallbackModel that exhausts its chain already tried EVERY provider this round.
    # Re-running the whole chain on the full retry budget multiplies latency by the chain
    # length (N providers per attempt) for little gain — if every provider is rate-limited
    # now, a few seconds of backoff won't clear it. So cap whole-chain re-runs hard and let
    # the run fail fast into graceful degradation instead of spinning to the expert timeout.
    chain_retries_left = settings.LLM.fallback_max_retries

    # ── budget reserve (inert unless settings.BUDGET.enforcement_enabled) ────────────────
    broker = budget_context.get_broker()
    reservation = None
    if broker is not None:
        scope = budget_context.current_scope(budget_mission_id)
        if scope is None:
            if not budget_context.is_exempt():
                # A wiring bug must be visible in prod, never silently unbilled — but this
                # call still RUNS (unbilled) rather than being blocked by its own metering gap.
                log.error(
                    "budget enforcement is ON but this call has no user_id scope (wiring bug) "
                    "-- running unbilled: model=%s", budget_model_id,
                )
        else:
            reservation = await broker.reserve(scope, budget_estimate_micros)

    settled = False
    start = time.monotonic()
    try:
        for attempt in range(attempts):
            try:
                result = await agent.run(*args, **kwargs)
                usage.accumulate(result)   # count this run's tokens into the active usage scope, if any
                if reservation is not None:
                    # A CALL THAT SUCCEEDED MUST NEVER BE TURNED INTO A FAILURE BY A METERING
                    # FAULT — this inner try/except is deliberately separate from the outer one
                    # (which decides retry-vs-raise): a pricing error here (e.g. an unpriced/
                    # empty `budget_model_id`) must degrade to "settle via the finally-refund
                    # below" and still return the real result, never re-enter the retry logic.
                    try:
                        input_tokens, output_tokens, _requests = usage.extract_usage(result)
                        # Priced against the LAYER's primary model (`budget_model_id`), not
                        # necessarily whichever fallback-chain member actually served this call —
                        # a rare-failover accuracy gap accepted alongside the anchor spec's other
                        # margin-safe approximations (still a real, priced model; never free).
                        actual_micros = call_cost_micros(ModelCall(
                            model_id=budget_model_id,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            elapsed_s=time.monotonic() - start,
                        ))
                        settled = await broker.reconcile(reservation, actual_micros)
                        if not settled:
                            # The broker swallowed a store fault internally (its contract: never
                            # raise here) and already logged it once. This is a DISTINGUISHABLE
                            # signal at this seam, not a repair — there is no out-of-band Postgres
                            # true-up yet (security review 2026-07-26, finding 2), so the finally
                            # block's own retry below is racing the same fault, not recovering
                            # from it. Loud on purpose: an unrefunded reservation past its TTL is
                            # a real overcharge, and this is the only record of it today.
                            log.error(
                                "budget reconcile returned failure for a SUCCESSFUL call "
                                "(model=%s) -- no working recovery path exists yet; the "
                                "reservation may go unrefunded if the fallback retry below "
                                "hits the same store fault", budget_model_id,
                            )
                    except Exception:  # noqa: BLE001 — see comment above
                        log.error(
                            "budget reconcile failed to price/settle a SUCCESSFUL call (model=%s) "
                            "-- falling back to a full refund via the finally block, never a charge "
                            "for an unmeasured cost", budget_model_id, exc_info=True,
                        )
                return result
            except Exception as exc:
                is_last = attempt == attempts - 1
                if is_last or not _is_transient(exc):
                    raise
                if isinstance(exc, BaseExceptionGroup):     # the whole fallback chain exhausted
                    if chain_retries_left <= 0:
                        raise
                    chain_retries_left -= 1
                await asyncio.sleep(min(delay, settings.LLM.retry_max_delay_s))
                delay *= 2
    finally:
        if reservation is not None and not settled:
            # Any exit without a successful reconcile above (raised, budget-exhausted, or any
            # other non-success path) refunds in FULL — the safe direction, and reconcile() is
            # idempotent so this can never double-settle against the one success path.
            refunded = await broker.reconcile(reservation, 0)
            if not refunded:
                # Last resort also failed against the same store fault the first attempt hit
                # (or this was the only attempt, on an exception path). No repair exists at
                # this seam today — this reservation is now stuck until its TTL expires
                # (security review 2026-07-26, finding 2; tracked as a go-live gate, not fixed
                # by this log line). Loud because it is the only remaining record of the leak.
                log.error(
                    "budget anchor: the fallback full refund ALSO failed for reservation %s "
                    "(model=%s) -- this reservation is stuck until its TTL expires",
                    reservation.reservation_id, budget_model_id,
                )
