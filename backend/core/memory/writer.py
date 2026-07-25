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

import settings
from foundation import MemoryKind, MemoryStore, MemoryWriteProposal
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


class _SupersessionVerdict(BaseModel):
    """The judge's verdict on whether NEW replaces EXISTING (EB1)."""
    supersedes: bool = False
    confident: bool = False
    rationale: str = ""


# the judged strings are already-distilled memories (short); keep the call cheap
_MAX_SUPERSESSION_CONTENT_CHARS = 1500
_SUPERSESSION_MAX_OUTPUT_TOKENS = 200


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
        retries=settings.MEMORY.distill_max_retries,
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


def _build_supersession_prompt(new_content: str, existing_content: str) -> str:
    return (
        f"## NEW\n{new_content[:_MAX_SUPERSESSION_CONTENT_CHARS]}\n\n"
        f"## EXISTING\n{existing_content[:_MAX_SUPERSESSION_CONTENT_CHARS]}\n"
    )


# CB2/CB3 graph-twin extraction — a memory's content is already short
# (dedup/policy-cleared), so this stays small and cheap by design.
_ENTITY_EXTRACT_MAX_CONTENT_CHARS = 1200
_ENTITY_EXTRACT_MAX_OUTPUT_TOKENS = 300
_MAX_ENTITIES = 8
_MAX_RELATIONS = 8


class _ExtractedEntity(BaseModel):
    """One named thing the memory is actually about."""
    name: str
    entity_type: str = "concept"


class _ExtractedRelation(BaseModel):
    """A directly-stated relationship between two extracted entities (by name)."""
    a: str
    b: str


class ExtractedEntities(BaseModel):
    """The extractor's structured verdict: named entities in one already-
    distilled memory, plus which pairs it directly relates. Both lists are
    commonly empty — most memories name zero or one entity and state no
    entity-to-entity relationship; that is the correct, common case, not a
    degraded result."""
    entities: list[_ExtractedEntity] = Field(default_factory=list)
    relates: list[_ExtractedRelation] = Field(default_factory=list)


def _build_entity_prompt(content: str) -> str:
    return f"## MEMORY\n{content[:_ENTITY_EXTRACT_MAX_CONTENT_CHARS]}\n"


async def extract_entities(content: str) -> ExtractedEntities:
    """CB2/CB3: pull named entities (and any directly-stated entity-to-entity
    relations) out of one already-accepted memory, for the knowledge-web graph
    twin. FAIL-CLOSED like every other writer step: any fault or malformed
    output returns an empty result — a missed graph twin is a smaller loss
    than a fabricated entity/link, and the memory itself already persisted
    independent of this step."""
    handle = build_agent(
        "memory",
        output_type=ExtractedEntities,
        prompt_name="memory_entities",
        retries=settings.MEMORY.distill_max_retries,
    )
    try:
        result = await run_structured(
            handle,
            _build_entity_prompt(content),
            max_turns=1,
            max_output_tokens=_ENTITY_EXTRACT_MAX_OUTPUT_TOKENS,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort; a fault must never affect the write that already landed
        log.warning("entity extraction failed: %s", exc)
        return ExtractedEntities()
    # Bounded regardless of what the model returned — a prompt is guidance,
    # never a guarantee, so the caller's fan-out into graph writes stays
    # bounded even on a model that ignores the "keep it short" instruction.
    return ExtractedEntities(
        entities=[e for e in result.entities if (e.name or "").strip()][:_MAX_ENTITIES],
        relates=[r for r in result.relates if (r.a or "").strip() and (r.b or "").strip()][:_MAX_RELATIONS],
    )


async def judge_supersession(new_content: str, existing_content: str) -> bool:
    """EB1: does `new_content` supersede `existing_content` — a later, updated
    version of the same specific fact/preference (not merely related content)?

    FAIL-CLOSED: returns False on any doubt, malformed output, or fault. A false
    positive would silently hide valid history — the one failure mode this
    refuses; a false negative just leaves both memories surfaced, which EB1
    accepts as correct (temporal truth, not erasure)."""
    handle = build_agent(
        "memory",
        output_type=_SupersessionVerdict,
        prompt_name="memory_supersession",
        retries=settings.MEMORY.distill_max_retries,
    )
    try:
        verdict = await run_structured(
            handle,
            _build_supersession_prompt(new_content, existing_content),
            max_turns=1,
            max_output_tokens=_SUPERSESSION_MAX_OUTPUT_TOKENS,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort; a fault must never mark a false supersession
        log.warning("supersession judgment failed: %s", exc)
        return False
    return bool(verdict.supersedes and verdict.confident)


class _ContradictionVerdict(BaseModel):
    """The judge's verdict on whether NEW directly contradicts EXISTING (§3.2)."""
    contradicts: bool = False
    confident: bool = False
    rationale: str = ""


# the judged strings are already-distilled memories (short); keep the call cheap
_MAX_CONTRADICTION_CONTENT_CHARS = 1500
_CONTRADICTION_MAX_OUTPUT_TOKENS = 200


def _build_contradiction_prompt(new_content: str, existing_content: str) -> str:
    return (
        f"## NEW\n{new_content[:_MAX_CONTRADICTION_CONTENT_CHARS]}\n\n"
        f"## EXISTING\n{existing_content[:_MAX_CONTRADICTION_CONTENT_CHARS]}\n"
    )


async def judge_contradiction(new_content: str, existing_content: str) -> bool:
    """§3.2 (knowledge-web CONTRADICTS edge): does `new_content` directly
    contradict `existing_content` — the same specific claim asserted
    incompatibly, not merely a different or unrelated claim about the same
    entity? Exact copy of `judge_supersession`'s fail-closed shape.

    FAIL-CLOSED: returns False on any doubt, malformed output, or fault. A
    false positive would assert a contradiction that isn't one — the refused
    failure mode; a false negative just leaves two claims unlinked, the
    honest default (most claims sharing an entity are NOT contradictory)."""
    handle = build_agent(
        "memory",
        output_type=_ContradictionVerdict,
        prompt_name="memory_contradiction",
        retries=settings.MEMORY.distill_max_retries,
    )
    try:
        verdict = await run_structured(
            handle,
            _build_contradiction_prompt(new_content, existing_content),
            max_turns=1,
            max_output_tokens=_CONTRADICTION_MAX_OUTPUT_TOKENS,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort; a fault must never assert a false contradiction
        log.warning("contradiction judgment failed: %s", exc)
        return False
    return bool(verdict.contradicts and verdict.confident)
