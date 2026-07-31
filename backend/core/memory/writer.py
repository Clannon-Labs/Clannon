"""Bounded LLM judgments used after write policy accepts a memory.

Turn-level relevance and tier selection live in ``curator.py``. This module owns
only one-shot enrichment/judgment calls: supersession, entity extraction, and
contradiction detection.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

import settings
from core.llm import build_agent, run_structured

log = logging.getLogger(__name__)

class _SupersessionVerdict(BaseModel):
    """The judge's verdict on whether NEW replaces EXISTING (EB1)."""
    supersedes: bool = False
    confident: bool = False
    rationale: str = ""


# the judged strings are already-distilled memories (short); keep the call cheap
_MAX_SUPERSESSION_CONTENT_CHARS = 1500
_SUPERSESSION_MAX_OUTPUT_TOKENS = 200

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
