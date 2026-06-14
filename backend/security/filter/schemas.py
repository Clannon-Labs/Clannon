"""Pydantic schema for the output filter's structured verdict."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FilterResult(BaseModel):
    """Strict output-filter verdict on a draft response."""
    proceed: bool
    blocked: bool = False
    reason: str | None = None
    categories: list[str] = Field(default_factory=list)
