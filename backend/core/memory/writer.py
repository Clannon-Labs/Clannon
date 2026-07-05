"""
The memory agent's distillation step.

After a turn completes, this runs the `memory`-layer LLM over (task, answer,
findings) and extracts what is worth keeping long-term:
  - SEMANTIC — durable, source-backed facts about the user's clients/domains.
  - PROCEDURAL — how this user likes to work: formats, conventions, recurring moves.

It only PROPOSES; the manager's write policy (confidence floor + dedup) decides
what actually persists. Best-effort: any fault returns no proposals, never raises.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from foundation import MemoryKind, MemoryStore, MemoryWriteProposal, constants
from core.llm import build_agent, run_structured

log = logging.getLogger(__name__)


def _coerce_kind(raw: str) -> MemoryKind:
    """The distiller only ever asserts FACT (source-backed) or ASSUMPTION
    (inferred). Anything else — including a blank or a garbled value — degrades to
    ASSUMPTION: LLM distillation is inferential by nature, so ASSUMPTION is the
    honest floor. UNSPECIFIED is reserved for legacy/untyped records, never for a
    memory the writer chose to keep."""
    return MemoryKind.FACT if (raw or "").strip().lower() == "fact" else MemoryKind.ASSUMPTION

# keep the distillation call cheap and bounded — it runs on every substantive turn
_MAX_TASK_CHARS = 1200
_MAX_ANSWER_CHARS = 3500
_MAX_FINDING_CHARS = 1000
_MAX_FINDINGS = 5
_MAX_OUTPUT_TOKENS = 700


class _Extracted(BaseModel):
    """One distilled memory the agent proposes."""
    content: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""
    # typed-knowledge (CB1): the agent classifies each memory. "assumption" is the
    # honest default — a distilled memory is inferential unless it is backed by a
    # cited source, in which case the agent says "fact" and names the `source`.
    kind: str = "assumption"
    source: str = ""


class MemoryExtraction(BaseModel):
    """The memory agent's structured verdict on a completed turn."""
    semantic: list[_Extracted] = Field(default_factory=list)
    procedural: list[_Extracted] = Field(default_factory=list)


def _build_prompt(task: str, answer: str, findings: list[str]) -> str:
    parts = [
        "A turn just finished (it may be research, a task, or a plain exchange). Distil "
        "only what is worth remembering long-term: durable facts the user shared or that "
        "the work established, and clear preferences for how they like things done. "
        "> Note: Donot save everything.. just save the summary or important things learnt "
        "from the answer delievered.\n",
        "For each memory, set `kind`: \"fact\" only when it is backed by a cited/"
        "verifiable source (name that source in `source`); otherwise \"assumption\" "
        "— an inference or a provisional belief that may later be revised.\n",
        f"## The user's request\n{(task or '')}\n",
        f"## The answer delivered\n{(answer or '')}\n",
    ]
    digest = [f[:_MAX_FINDING_CHARS] for f in findings[:_MAX_FINDINGS] if f]
    if digest:
        parts.append("## Supporting findings\n" + "\n---\n".join(digest))
    return "\n".join(parts)


async def distill(task: str, answer: str, findings: list[str]) -> list[MemoryWriteProposal]:
    """Run the memory agent and return its proposed semantic/procedural writes.
    Returns [] on any failure — distillation never breaks a turn."""
    handle = build_agent(
        "memory",
        output_type=MemoryExtraction,
        prompt_name="memory",
        retries=constants.MEMORY_DISTILL_MAX_RETRIES,
    )
    try:
        result = await run_structured(
            handle,
            _build_prompt(task, answer, findings),
            max_turns=1,
            max_output_tokens=_MAX_OUTPUT_TOKENS,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort; a fault must not affect the turn
        log.warning("memory distillation failed: %s", exc)
        return []

    proposals: list[MemoryWriteProposal] = []
    for tier, items in (
        (MemoryStore.SEMANTIC, result.semantic),
        (MemoryStore.PROCEDURAL, result.procedural),
    ):
        for item in items:
            content = (item.content or "").strip()
            if content:
                proposals.append(MemoryWriteProposal(
                    store=tier,
                    content=content,
                    rationale=item.rationale,
                    confidence=item.confidence,
                    kind=_coerce_kind(item.kind),
                    source=(item.source or "").strip(),
                ))
    return proposals
