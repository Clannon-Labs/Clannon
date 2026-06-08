"""
Output filter stage — the final gate before delivery.

Mirrors the verifier: a small, fast structured-output LLM (role `filter`) checks
the orchestrator's draft response for safety/policy and basic groundedness, using
the buffered expert findings as the grounding context. It runs on the final
response only — never on the decision-log stream. On block it stops the chain
(delivery is skipped) so unsafe content never reaches the user; there is no
re-orchestration retry loop at the checkpoint.
"""

from __future__ import annotations

import json
import time
from typing import Any

from foundation import (
    BlockReason,
    FilterError,
    Flow,
    ModelUnavailableError,
    Origin,
    PipelineStage,
    ThreatLevel,
    constants,
)
from core.llm import build_agent, run_structured

from .schemas import FilterResult


def _grounding_view(response, findings: list) -> str:
    sources: list[str] = []
    for finding in findings:
        sources.extend(getattr(finding, "citations", []) or [])
    view = {
        "draft": getattr(response, "text", ""),
        "expert_findings": len(findings),
        "sources": sources[:20],
    }
    return json.dumps(view, default=str)


async def _filter(response, findings: list) -> FilterResult:
    handle = build_agent(
        "filter",
        output_type=FilterResult,
        prompt_name="filter",
        retries=constants.FILTER_MAX_RETRIES,
    )
    return await run_structured(handle, _grounding_view(response, findings))


async def run(flow: Flow[Any]) -> Flow[Any]:
    """Pipeline entry point for the output filter."""
    started = time.monotonic()
    try:
        flow.ctx.advance(PipelineStage.FILTERING)
        response = flow.ctx.orchestrator_response
        if response is None:
            # Nothing to filter (no draft produced); pass the flow through unchanged.
            return flow.next(await flow.load(), Origin.FILTER, started)

        result = await _filter(response, flow.ctx.expert_findings)
        flow.ctx.filter_result = result

        if not result.proceed:
            flow.ctx.filter_blocked = True
            flow.ctx.filter_block_reason = result.reason
            return flow.block(BlockReason.FILTER_REJECTED, ThreatLevel.MEDIUM, Origin.FILTER, started)

        flow.ctx.filter_blocked = False
        return flow.next(response, Origin.FILTER, started)

    except (FilterError, ModelUnavailableError) as exc:
        return flow.fail(exc, Origin.FILTER, started)
    except Exception as exc:
        return flow.fail(FilterError(f"output filter failed: {exc}"), Origin.FILTER, started)
