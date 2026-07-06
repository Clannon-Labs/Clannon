"""
foundation/vocab/types.py

Shared primitive types for Vraksha.

These are the vocabulary the entire system speaks.
No layer defines its own version of these — they import from here.

Rule: if two or more layers would independently define the same concept,
it belongs here instead.

Usage:
    from foundation import Modality, ThreatLevel, BlockReason
"""

from __future__ import annotations

from enum import Enum


# ---------------------------------------------------------------------------
# Pipeline origins
# Used by: flow, transport, sanitizers, verifier, filter, handlers, memory
# ---------------------------------------------------------------------------

class Origin(str, Enum):
    """
    Which stage produced a Flow or Envelope.
    Carried in Flow.meta.origin and JournalEntry.origin.
    Every stage passes its own Origin value to flow.next(),
    flow.block(), flow.fail(), and flow.warn().
    """
    INTAKE          = "intake"
    SANITIZER       = "sanitizer"
    VERIFIER        = "verifier"
    NORMALIZER      = "normalizer"
    ORCHESTRATOR    = "orchestrator"
    TOOL_HANDLER    = "tool_handler"
    EXPERT_HANDLER  = "expert_handler"
    FILTER          = "filter"
    OUTPUT          = "output"
    MEMORY          = "memory"
    SYSTEM          = "system"      # internal system messages, not LLM

# ---------------------------------------------------------------------------
# Input modalities
# Used by: intake, sanitizers, context, normalizer
# ---------------------------------------------------------------------------

class Modality(str, Enum):
    """
    The type of content detected in a user's input.
    One input can contain multiple modalities (e.g. a PDF with embedded images).
    intake.py detects these and populates ctx.detected_modalities.
    Each modality gets its own sanitizer worker.
    """
    TEXT  = "text"
    PDF   = "pdf"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    UNSUPPORTED_MODALITY = "unsupported"


# ---------------------------------------------------------------------------
# Threat classification
# Used by: sanitizers, verifier, filter, context, dead letter writer
# ---------------------------------------------------------------------------

class ThreatLevel(str, Enum):
    """
    How dangerous something was judged to be.
    Produced by sanitizers and the verifier LLM.
    Determines whether the pipeline blocks, warns, or proceeds.

    NONE     — clean, no threat detected
    LOW      — minor flag, pipeline proceeds with a WARN envelope
    MEDIUM   — significant flag, orchestrator is informed but proceeds
    HIGH     — serious threat, pipeline is blocked
    CRITICAL — severe threat (e.g. CBRN, CSAM adjacent), hard block,
               dead letter written, never reaches orchestrator
    """
    NONE     = "none"
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"

    @property
    def should_block(self) -> bool:
        """True if this threat level must stop the pipeline."""
        return self in (ThreatLevel.HIGH, ThreatLevel.CRITICAL)

    @property
    def should_warn(self) -> bool:
        """True if this threat level should warn but not block."""
        return self in (ThreatLevel.LOW, ThreatLevel.MEDIUM)


class BlockReason(str, Enum):
    """
    Why a request was blocked.
    Written to Envelope.reason and ctx.block_reason.
    Used in dead letter output and internal logs.
    Never shown verbatim to users — user sees a generic system message.

    MALFORMED_INPUT      — input was empty, unreadable, or structurally invalid
    MALICIOUS_CONTENT    — sanitizer detected a threat in the input
    INJECTION_DETECTED   — prompt injection found in text or embedded content
    VERIFIER_REJECTED    — verifier LLM classified input as dangerous
    FILTER_REJECTED      — output filter rejected orchestrator's response
    INPUT_TOO_LARGE      — input exceeded size limits
    RATE_LIMITED         — request exceeded intake rate limits
    UNSUPPORTED_MODALITY — input contains a modality we don't handle
    POLICY_VIOLATION     — content violates a hardcoded policy (not LLM judgment)
    MAX_RETRIES_EXCEEDED — filter retry loop exhausted without a clean response
    """
    MALFORMED_INPUT      = "malformed_input"
    MALICIOUS_CONTENT    = "malicious_content"
    INJECTION_DETECTED   = "injection_detected"
    VERIFIER_REJECTED    = "verifier_rejected"
    FILTER_REJECTED      = "filter_rejected"
    INPUT_TOO_LARGE      = "input_too_large"
    RATE_LIMITED         = "rate_limited"
    UNSUPPORTED_MODALITY = "unsupported_modality"
    POLICY_VIOLATION     = "policy_violation"
    MAX_RETRIES_EXCEEDED = "max_retries_exceeded"


# -------------------------------------------------------------------------------------
# Tool and expert permission levels
# Used by: universal registry or tool registry, expert registry, handlers, orchestrator
# --------------------------------------------------------------------------------------

class PermissionLevel(str, Enum):
    """
    Access tier for tools and experts.
    Every tool and expert declares its required PermissionLevel.
    Experts are granted up to their predefined level by default.
    Anything above requires orchestrator approval + user confirmation.

    READ     — can only read data, no side effects
    WRITE    — can write or modify data
    EXECUTE  — can run code or shell commands
    NETWORK  — can make external network calls
    ELEVATED — combines multiple levels, requires explicit user grant
    """
    READ     = "read"
    WRITE    = "write"
    EXECUTE  = "execute"
    NETWORK  = "network"
    ELEVATED = "elevated"


# ---------------------------------------------------------------------------
# Memory store types
# Used by: memory manager, memory writer, orchestrator
# ---------------------------------------------------------------------------

class MemoryStore(str, Enum):
    """
    Which memory store a read or write targets.
    Maps to concrete store implementations in memory/stores/.

    WORKING    — short term, current session only, lost on session end
    EPISODIC   — conversation history, persisted across sessions
    SEMANTIC   — facts and knowledge, stored in qdrant, semantic search
    WIKI       — highest-trust, user-authored .md knowledge; overrides inferred
    PROCEDURAL — skills, habits, repeatable workflows and preferences

    The four durable tiers (wiki, semantic, episodic, procedural) mirror the
    architecture's memory model; WORKING is the ephemeral session cache.
    """
    WORKING    = "working"
    EPISODIC   = "episodic"
    SEMANTIC   = "semantic"
    WIKI       = "wiki"
    PROCEDURAL = "procedural"


class MemoryKind(str, Enum):
    """
    The kind of a stored memory.

    UNSPECIFIED / FACT / ASSUMPTION are the EPISTEMIC axis — is the record asserted
    or inferred? UNSPECIFIED is the default for legacy/untyped records; a record is
    never silently promoted to a type it was not assigned; the writer sets FACT vs
    ASSUMPTION explicitly at distillation time.

    DECISION is a CATEGORY, not an epistemic status (a decision is itself asserted —
    trust-rank it with FACT). It is marked distinctly because a decision record is
    (a) queryable as a category — EB2's "recent decisions" — and (b) HISTORY-CRITICAL:
    a decision must never be silently collapsed by the dedup-merge path. A near-identical
    later revision SUPERSEDES via the EB1 judge (both records retained), so the original
    reasoning is never lost — CB4's literal "reasoning is lost / discussion cannot be
    reconstructed" fail condition. The append-only guarantee lives in the core/memory
    dedup exemption; this value is the hook it keys on.
    """
    UNSPECIFIED = "unspecified"  # legacy / untyped — the honest default
    FACT        = "fact"         # asserted, source-backed knowledge
    ASSUMPTION  = "assumption"   # inferred / provisional; may be revised
    DECISION    = "decision"     # institutional decision record (CB4); asserted, but
                                 # append-only — supersede, never dedup-overwrite


# ---------------------------------------------------------------------------
# Batch lifecycle (batch architecture — the control-plane status axis)
# Used by: the BatchAwarenessPort contract + its core/memory implementer
# ---------------------------------------------------------------------------

class BatchLifecycleStatus(str, Enum):
    """A batch orchestrator's current status, for the cross-batch awareness slice.

    This is CONTROL-PLANE state (where a batch is in its lifecycle), a deliberately
    separate axis from `MemoryKind` (which is epistemic — what a stored fact IS). That
    separation is why batch awareness rides its OWN `BatchAwarenessPort`, not `MemoryPort`
    (ratified 2026-07-05). A quiet BLOCKED/FAILED batch is the high-signal case the slice
    exists to surface, so it must survive truncation over a wave of ACTIVE ones."""
    ACTIVE  = "active"
    BLOCKED = "blocked"
    DONE    = "done"
    FAILED  = "failed"
