"""
Fast deterministic text-risk rules for the verifier.

These rules are a hint source for the LLM verifier, not a content blocker. They
run before the LLM call (cheap, regex-only) and record a score/categories so the
LLM has a strong prior, but they never decide block/warn on their own — the LLM
verifier is the sole content judge for text (see verifier.run). This keeps the
fast path fast without turning a single regex match into a false-positive wall.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from foundation import NormalizedInput, ThreatLevel

from .schemas import VerificationResult
from .utils import content_excerpt, verification_result


@dataclass(frozen=True, slots=True)
class InjectionRule:
    """One deterministic text rule feeding the LLM verifier a risk hint."""
    name: str
    pattern: re.Pattern[str]
    category: str
    weight: int


INJECTION_RULES = [
    InjectionRule(
        name="ignore_instructions",
        pattern=re.compile(
            r"\b(ignore|bypass|override|forget|disregard)\b.{0,80}"
            r"\b(previous|prior|above|system|developer|safety|policy|instructions?)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        category="prompt_injection",
        weight=4,
    ),
    InjectionRule(
        name="role_redefinition",
        pattern=re.compile(
            r"\b(you are now|act as|simulate|pretend to be)\b.{0,80}"
            r"\b(unrestricted|unfiltered|jailbroken|developer mode|no rules)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        category="jailbreak",
        weight=4,
    ),
    InjectionRule(
        name="prompt_exfiltration",
        pattern=re.compile(
            r"\b(reveal|print|show|dump|output|exfiltrate|leak)\b.{0,80}"
            r"\b(system prompt|developer message|hidden instructions|policy|tool schema|secrets?)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        category="prompt_exfiltration",
        weight=5,
    ),
    InjectionRule(
        name="tool_abuse",
        pattern=re.compile(
            r"\b(call|use|invoke|run)\b.{0,80}"
            r"\b(tool|function|shell|terminal|python|browser)\b.{0,80}"
            r"\b(ignore|bypass|without permission|secretly|silently)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        category="tool_abuse",
        weight=4,
    ),
    InjectionRule(
        name="credential_theft",
        pattern=re.compile(
            r"\b(steal|harvest|extract|phish|exfiltrate)\b.{0,80}"
            r"\b(api keys?|tokens?|passwords?|credentials?|cookies?)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        category="credential_theft",
        weight=5,
    ),
    InjectionRule(
        name="malware_intent",
        pattern=re.compile(
            r"("
            r"\b(write|create|build|generate|deploy|install|hide|obfuscate|execute)\b.{0,80}"
            r"\b(malware|ransomware|keylogger|botnet|reverse shell|persistence|payload)\b"
            r"|"
            r"\b(malware|ransomware|keylogger|botnet|reverse shell|payload)\b.{0,80}"
            r"\b(write|create|build|generate|deploy|install|hide|obfuscate|execute)\b"
            r")",
            re.IGNORECASE | re.DOTALL,
        ),
        category="malicious_code",
        weight=4,
    ),
    InjectionRule(
        name="instruction_boundary_marker",
        pattern=re.compile(
            r"\b(begin|end)\s+(system|developer|hidden)\s+(prompt|message|instructions?)\b",
            re.IGNORECASE,
        ),
        category="prompt_injection",
        weight=3,
    ),
]


def scan_text_risk(normalized: NormalizedInput) -> VerificationResult:
    """
    Produce a deterministic risk *hint*, never a block.

    Regex matches are recorded as deterministic_score / matched_rules /
    categories in metadata for the LLM verifier to weigh; this function always
    returns proceed=True with ThreatLevel.NONE. The LLM verifier makes the
    actual content decision (see verifier.run). Structural problems
    (unsupported modality, missing capability) are still hard-blocked upstream
    in verify_handoff / verify_routing — those are correctness, not content
    judgment.
    """
    excerpt, truncated = content_excerpt(normalized.content)

    matches = []
    score = 0
    categories = set()

    for rule in INJECTION_RULES:
        if excerpt and rule.pattern.search(excerpt):
            score += rule.weight
            categories.add(rule.category)
            matches.append(rule.name)

    metadata = {
        "deterministic_score": score,
        "matched_rules": matches,
        "excerpt_chars": len(excerpt),
        "excerpt_truncated": truncated,
        "suspected": bool(matches),
    }

    return verification_result(
        proceed=True,
        threat_level=ThreatLevel.NONE,
        categories=sorted(categories),
        normalized=normalized,
        metadata=metadata,
    )
