"""Pydantic schemas used by the verifier LLM."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class VerifierInputView(BaseModel):
    """Compact, safe view sent to the verifier model."""
    modality: str
    content_type: str
    content_excerpt: str
    deterministic_categories: list[str] = Field(default_factory=list)
    deterministic_score: int = 0
    matched_rules: list[str] = Field(default_factory=list)
    excerpt_truncated: bool = False
    sanitizer_summary: dict = Field(default_factory=dict)
    target_provider: str | None = None
    target_model: str | None = None


class VerifierLLMResult(BaseModel):
    """Strict verifier-model output."""
    proceed: bool
    dangerous: bool = False
    warn: bool = False
    threat_level: Literal["none", "low", "medium", "high", "critical"]
    reason: str | None = None
    categories: list[str] = Field(default_factory=list)
