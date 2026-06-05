"""
types.py

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

    MALICIOUS_CONTENT    — sanitizer detected a threat in the input
    INJECTION_DETECTED   — prompt injection found in text or embedded content
    VERIFIER_REJECTED    — verifier LLM classified input as dangerous
    FILTER_REJECTED      — output filter rejected orchestrator's response
    INPUT_TOO_LARGE      — input exceeded size limits
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

    WORKING   — short term, current session only, lost on session end
    EPISODIC  — conversation history, persisted across sessions
    SEMANTIC  — facts and knowledge, stored in qdrant, semantic search
    """
    WORKING  = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


# ---------------------------------------------------------------------------
# Expert states
# Used by: expert registry, expert handler, orchestrator
# ---------------------------------------------------------------------------

class ExpertState(str, Enum):
    """
    Current operational state of an expert.
    The orchestrator reads this from the registry before invoking.
    It will not invoke an expert that is not AVAILABLE.

    AVAILABLE   — ready to receive work
    BUSY        — currently processing another invocation
    UNAVAILABLE — offline, errored, or circuit broken
    RESTRICTED  — available but with reduced tool permissions
    """
    AVAILABLE   = "available"
    BUSY        = "busy"
    UNAVAILABLE = "unavailable"
    RESTRICTED  = "restricted"
