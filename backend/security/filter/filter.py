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

import settings
from foundation import (
    BlockReason,
    FilterError,
    Flow,
    ModelUnavailableError,
    Origin,
    PipelineStage,
    ThreatLevel,
)
from core.llm import build_agent, run_structured

from .schemas import FilterResult


# bounds on the grounding payload — enough evidence for the filter to judge
# groundedness without blowing up the filter call's token cost. Sourced from
# config/backend/security.yaml (settings.SECURITY, docket D8: floor + 4x ceiling).
_MAX_FINDINGS = settings.SECURITY.filter_grounding_max_findings
_FINDING_CHARS = settings.SECURITY.filter_grounding_max_finding_chars
_MAX_TOOL_CALLS = settings.SECURITY.filter_grounding_max_tool_calls
_TOOL_RESULT_CHARS = settings.SECURITY.filter_grounding_max_tool_result_chars


def _grounding_view(response, findings: list, memory: list, tool_calls: list) -> str:
    sources: list[str] = []
    evidence: list[dict] = []
    for finding in findings[:_MAX_FINDINGS]:
        citations = list(getattr(finding, "citations", []) or [])
        sources.extend(citations)
        # the filter MUST see the actual findings content to assess whether the
        # draft's claims are grounded — a count and a URL list are not enough
        evidence.append({
            "expert": getattr(finding, "expert", ""),
            "content": getattr(finding, "full_content", "")[:_FINDING_CHARS],
            "citations": citations,
        })
    # the orchestrator's OWN tool calls (e.g. web_search, fetch_url) are grounding
    # too — a turn can research directly without spawning an expert, and the draft
    # is grounded in those results just as much as in expert findings.
    tool_evidence: list[dict] = []
    for tc in tool_calls[:_MAX_TOOL_CALLS]:
        if not getattr(tc, "success", False):
            continue
        tool_evidence.append({
            "tool": getattr(tc, "tool_name", ""),
            "args": getattr(tc, "arguments", {}),
            "result": str(getattr(tc, "result", ""))[:_TOOL_RESULT_CHARS],
        })
    view = {
        "draft": getattr(response, "text", ""),
        # The recipient is the SAME single authenticated user who made the request.
        # Their OWN information — what they just provided or asked the assistant to
        # remember — echoed back to them (confirming a saved name, preference, rate,
        # or client detail) is NOT a third-party PII leak. PII/secret blocking is for
        # data being exfiltrated to someone who should not see it, not for the user's
        # own data returning to the user. Don't block memory-update confirmations.
        "recipient": "the same single authenticated user who made this request",
        # whether this turn actually researched — via experts OR direct tool calls.
        # False ⇒ a direct/conversational answer, which groundedness does not apply to.
        "did_research": bool(evidence or tool_evidence),
        # the evidence the draft was synthesized from — claims supported here are grounded
        "expert_findings": evidence,
        "tool_results": tool_evidence,
        "sources": sources[:20],
        # hydrated memory is a LEGITIMATE grounding source: claims supported
        # by these entries are grounded, not hallucinated
        "memory_grounding": [getattr(m, "content", str(m))[:300] for m in memory[:10]],
    }
    return json.dumps(view, default=str)


async def _filter(response, findings: list, memory: list, tool_calls: list) -> FilterResult:
    handle = build_agent(
        "filter",
        output_type=FilterResult,
        prompt_name="filter",
        retries=settings.SECURITY.filter_max_retries,
    )
    return await run_structured(handle, _grounding_view(response, findings, memory, tool_calls))


async def run(flow: Flow[Any]) -> Flow[Any]:
    """Pipeline entry point for the output filter."""
    started = time.monotonic()
    try:
        flow.ctx.advance(PipelineStage.FILTERING)
        response = flow.ctx.orchestrator_response
        if response is None:
            # Nothing to filter (no draft produced); pass the flow through unchanged.
            return flow.next(await flow.load(), Origin.FILTER, started)

        result = await _filter(
            response, flow.ctx.expert_findings, flow.ctx.hydration_items, flow.ctx.tool_calls
        )
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
        return flow.fail(FilterError(f"output filter failed: {exc}", cause=exc), Origin.FILTER, started)
