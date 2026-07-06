"""Pydantic schema for the output filter's structured verdict."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FilterResult(BaseModel):
    """Strict output-filter verdict on a draft response.

    `groundedness`/`checks_performed` are the CB5 "earned seal" — populated on every
    call (pass or block), not just blocks, so a PASS carries a real, inspectable
    attestation instead of a silent no-op (`docs/benchmarks/V1_GAP_ANALYSIS.md`). A
    safe-but-thinly-grounded draft can legitimately be `proceed=True` with
    `groundedness="partial"` — do not read `proceed=True` as implying `"grounded"`.
    """
    proceed: bool
    blocked: bool = False
    reason: str | None = None
    categories: list[str] = Field(default_factory=list)
    groundedness: Literal["grounded", "partial", "ungrounded", "not_applicable"] = "not_applicable"
    checks_performed: list[str] = Field(default_factory=list)
