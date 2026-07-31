"""Memory Manager-owned, tool-driving curation of one completed turn.

Tools capture trusted turn scope in a per-run closure. The model can search and
stage typed actions, but cannot name a user or touch storage. Staged actions
persist only after a successful final verdict, so a curator fault writes nothing.
"""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel

import settings
from core.llm import build_tool_agent, run_structured
from foundation import MemoryItem, MemoryKind, MemoryStore, MemoryTurn, MemoryWriteProposal
from registry.config import get_prompt

from . import embeddings, store, write_policy

log = logging.getLogger(__name__)

_INFERRED_TIERS = (
    MemoryStore.SEMANTIC,
    MemoryStore.EPISODIC,
    MemoryStore.PROCEDURAL,
)
_MAX_TOOL_SEARCH_RESULTS = 10
_MAX_RATIONALE_CHARS = 600
_MAX_SOURCE_CHARS = 600
_MAX_PARTICIPANTS_CHARS = 1_000
_MAX_REQUEST_CHARS = 3_000
_MAX_RESPONSE_CHARS = 5_000
_MAX_EVIDENCE_ITEMS = 8
_MAX_EVIDENCE_CHARS = 1_000


class CuratedTier(str, Enum):
    """Only tiers the curator may infer. WIKI and WORKING are unrepresentable."""

    SEMANTIC = MemoryStore.SEMANTIC.value
    EPISODIC = MemoryStore.EPISODIC.value
    PROCEDURAL = MemoryStore.PROCEDURAL.value


class CuratorVerdict(BaseModel):
    """Final agent signal. Tool actions remain staged until this succeeds."""

    complete: bool = True
    rationale: str = ""


def _looks_like_transcript(content: str, turn: MemoryTurn) -> bool:
    """Reject literal turn copies; episodic memory records meaning, not chat."""
    normalized = " ".join(content.casefold().split())
    if normalized in {
        " ".join((turn.request or "").casefold().split()),
        " ".join((turn.response or "").casefold().split()),
    }:
        return True
    transcript_pairs = (
        ("task:", "answer:"),
        ("request:", "response:"),
        ("user:", "assistant:"),
    )
    return any(left in normalized and right in normalized for left, right in transcript_pairs)


async def _search_existing(user_id: str, query: str, limit: int) -> list[dict[str, object]]:
    """Search inferred tiers under the captured tenant scope."""
    text = (query or "").strip()[: settings.MEMORY.max_content_chars]
    if not text:
        return []
    try:
        vectors = await asyncio.wait_for(
            embeddings.embed([text]),
            timeout=settings.MEMORY.read_timeout_s,
        )
    except Exception as exc:  # noqa: BLE001 - search is optional curator context
        log.warning("curator memory search degraded: %s", exc)
        return []
    if not vectors:
        return []

    per_tier = await asyncio.gather(
        *(
            asyncio.to_thread(store.search, tier, user_id, vectors[0], limit)
            for tier in _INFERRED_TIERS
        ),
        return_exceptions=True,
    )
    hits: list[dict[str, object]] = []
    for tier, result in zip(_INFERRED_TIERS, per_tier):
        if isinstance(result, BaseException):
            log.warning("curator %s search degraded: %s", tier.value, result)
            continue
        hits.extend(
            {
                "memory_id": hit.get("id", ""),
                "tier": tier.value,
                "content": hit.get("content", ""),
                "kind": hit.get("kind", MemoryKind.UNSPECIFIED.value),
                "source": hit.get("source", ""),
                "confidence": float(hit.get("confidence", 0.0)),
                "score": float(hit.get("score", 0.0)),
            }
            for hit in result
        )
    hits.sort(key=lambda hit: float(hit["score"]), reverse=True)
    return hits[:limit]


@dataclass(slots=True)
class _CuratorSession:
    """Per-run trusted scope plus model-staged actions."""

    turn: MemoryTurn
    staged: list[MemoryWriteProposal] = field(default_factory=list)
    tool_calls: int = 0

    def _take_tool_call(self) -> None:
        self.tool_calls += 1
        if self.tool_calls > settings.MEMORY.curator_max_turns:
            raise RuntimeError("memory curator tool-call cap exceeded")

    async def search_memory(self, query: str, limit: int = 5) -> list[dict[str, object]]:
        """Search existing durable memory for this same authenticated user."""
        self._take_tool_call()
        bounded_limit = max(1, min(int(limit), _MAX_TOOL_SEARCH_RESULTS))
        return await _search_existing(self.turn.user_id, query, bounded_limit)

    async def save_memory(
        self,
        tier: CuratedTier,
        content: str,
        rationale: str,
        confidence: float,
        kind: MemoryKind,
        source: str = "",
        valid_at: float = 0.0,
    ) -> str:
        """Stage one self-contained durable memory for deterministic policy."""
        self._take_tool_call()
        try:
            safe_tier = CuratedTier(tier)
            safe_kind = MemoryKind(kind)
        except (TypeError, ValueError):
            return "rejected: tier or epistemic kind is not curator-writable"

        text = (content or "").strip()
        why = (rationale or "").strip()
        origin = (source or "").strip()
        if not text or len(text) > settings.MEMORY.max_content_chars:
            return "rejected: content is empty or exceeds the hard size cap"
        if not why or len(why) > _MAX_RATIONALE_CHARS:
            return "rejected: rationale is empty or exceeds the hard size cap"
        if len(origin) > _MAX_SOURCE_CHARS:
            return "rejected: source exceeds the hard size cap"
        if safe_kind is MemoryKind.UNSPECIFIED:
            return "rejected: every curated memory needs an epistemic kind"
        if safe_kind is MemoryKind.FACT and not origin:
            return "rejected: a fact requires a source"
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            return "rejected: confidence must be between zero and one"
        if confidence < settings.MEMORY.min_accept_confidence:
            return "rejected: confidence is below deterministic write policy"
        if not math.isfinite(valid_at) or valid_at < 0.0:
            return "rejected: valid_at must be a non-negative timestamp"
        if _looks_like_transcript(text, self.turn):
            return "rejected: durable memory cannot be a transcript copy"

        participants = ",".join(
            participant.strip()
            for participant in self.turn.participants
            if participant.strip()
        )[:_MAX_PARTICIPANTS_CHARS]
        self.staged.append(
            MemoryWriteProposal(
                store=MemoryStore(safe_tier.value),
                content=text,
                rationale=why,
                confidence=confidence,
                kind=safe_kind,
                valid_at=valid_at,
                source=origin,
                participants=participants,
            )
        )
        return "staged: deterministic policy will decide persistence after curator completion"

    def tools(self) -> tuple[object, ...]:
        """Expose only typed, scope-captured functions to the LLM seam."""
        return (self.search_memory, self.save_memory)


def _turn_prompt(turn: MemoryTurn) -> str:
    """Bound neutral turn evidence independently of prompt guidance."""
    parts = [
        f"## REQUEST\n{(turn.request or '')[:_MAX_REQUEST_CHARS]}",
        f"## DELIVERED RESPONSE\n{(turn.response or '')[:_MAX_RESPONSE_CHARS]}",
    ]
    findings = [
        item[:_MAX_EVIDENCE_CHARS]
        for item in turn.findings[:_MAX_EVIDENCE_ITEMS]
        if item
    ]
    decisions = [
        item[:_MAX_EVIDENCE_CHARS]
        for item in turn.decisions[:_MAX_EVIDENCE_ITEMS]
        if item
    ]
    if findings:
        parts.append("## FINDINGS\n" + "\n---\n".join(findings))
    if decisions:
        parts.append("## DECISION LOG EVIDENCE\n" + "\n---\n".join(decisions))
    return "\n\n".join(parts)


async def process_turn(turn: MemoryTurn) -> list[MemoryItem]:
    """Let the manager's LLM curate one turn, then persist accepted tool actions."""
    if not turn.user_id:
        return []
    session = _CuratorSession(turn)
    try:
        handle = build_tool_agent(
            "memory",
            output_type=CuratorVerdict,
            system_prompt=get_prompt("memory").text,
            tools=session.tools(),
            retries=settings.MEMORY.distill_max_retries,
        )
        verdict = await run_structured(
            handle,
            _turn_prompt(turn),
            max_turns=settings.MEMORY.curator_max_turns,
            max_output_tokens=settings.MEMORY.curator_max_output_tokens,
        )
    except Exception as exc:  # noqa: BLE001 - curation never affects delivered output
        log.warning("memory curator failed; staged actions discarded: %s", exc)
        return []
    if not verdict.complete or not session.staged:
        return []
    try:
        return await write_policy.persist_curated(turn, session.staged)
    except Exception as exc:  # noqa: BLE001 - memory remains best-effort after delivery
        log.warning("memory curator persistence degraded: %s", exc)
        return []
