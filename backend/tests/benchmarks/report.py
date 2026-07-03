"""Shared report helper for the benchmark acceptance harnesses.

Every harness builds one ``BenchmarkReport``: a benchmark id + title, one
``RequirementResult`` per documented pass requirement, an optional per-case table,
and free-form notes that name any honest gap. ``render()`` turns it into a stable,
greppable text block; ``overall()`` rolls the requirement verdicts up to a single
benchmark verdict.

This module is deliberately generic so the C1 / C4 / C3 / E1 harnesses and the
consolidated scoreboard (the other queued benchmark tasks) reuse it unchanged. It
has no dependency on any Clannon module — it is pure reporting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Verdict(str, Enum):
    """A benchmark / requirement outcome.

    PASS         — requirement met and hermetically certified here.
    PARTIAL      — partially met; the report's reason states exactly what is and
                   is not covered (e.g. a layer that is only live-certified).
    NOT_YET      — capability not implemented yet (an honest, expected gap, often
                   gated on a maintainer decision); never a test failure.
    FAIL         — requirement is contradicted by observed behavior. A real defect.
    NOT_MEASURED — no harness exercised this requirement yet.
    """

    PASS = "PASS"
    PARTIAL = "PARTIAL"
    NOT_YET = "NOT-YET"
    FAIL = "FAIL"
    NOT_MEASURED = "NOT-MEASURED"

    @property
    def is_failure(self) -> bool:
        """True only for a genuine defect. NOT_YET / PARTIAL are honest reads."""
        return self is Verdict.FAIL


# Worst-wins ordering for rolling requirement verdicts up to a benchmark verdict.
# A single FAIL dominates; otherwise any PARTIAL/NOT_YET makes the whole benchmark
# PARTIAL; an all-PASS benchmark is PASS; an empty/unmeasured one is NOT_MEASURED.
_SEVERITY = {
    Verdict.PASS: 0,
    Verdict.NOT_MEASURED: 1,
    Verdict.NOT_YET: 2,
    Verdict.PARTIAL: 3,
    Verdict.FAIL: 4,
}


@dataclass(frozen=True)
class RequirementResult:
    """One documented pass requirement and how the harness scored it."""

    key: str          # short stable id, e.g. "detect"
    title: str        # human label, e.g. "Detect attack"
    verdict: Verdict
    reason: str       # one line: why this verdict, what is / isn't covered
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class CaseRow:
    """One per-payload (or per-item) row in the harness's detail table."""

    id: str
    outcome: str          # e.g. "blocked" / "passed"
    detail: str = ""


@dataclass
class BenchmarkReport:
    """A structured, renderable result for one benchmark."""

    benchmark_id: str         # e.g. "C5"
    title: str                # e.g. "Security Validation"
    requirement_summary: str = ""  # e.g. "detect / classify / explain / prevent / audit"
    requirements: list[RequirementResult] = field(default_factory=list)
    cases: list[CaseRow] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    # -- builders ---------------------------------------------------------
    def add_requirement(
        self,
        key: str,
        title: str,
        verdict: Verdict,
        reason: str,
        evidence: tuple[str, ...] | list[str] = (),
    ) -> None:
        self.requirements.append(
            RequirementResult(key, title, verdict, reason, tuple(evidence))
        )

    def add_case(self, id: str, outcome: str, detail: str = "") -> None:
        self.cases.append(CaseRow(id, outcome, detail))

    def add_note(self, note: str) -> None:
        self.notes.append(note)

    # -- rollup -----------------------------------------------------------
    def overall(self) -> Verdict:
        """Worst-wins rollup of the requirement verdicts."""
        if not self.requirements:
            return Verdict.NOT_MEASURED
        return max((r.verdict for r in self.requirements), key=lambda v: _SEVERITY[v])

    def has_failure(self) -> bool:
        """True if any requirement is a genuine defect (FAIL)."""
        return any(r.verdict.is_failure for r in self.requirements)

    # -- rendering --------------------------------------------------------
    def render(self) -> str:
        bar = "=" * 74
        lines: list[str] = [
            bar,
            f"BENCHMARK {self.benchmark_id} — {self.title}",
            f"OVERALL: {self.overall().value}",
            bar,
        ]

        suffix = f"  ({self.requirement_summary})" if self.requirement_summary else ""
        lines.append(f"Pass requirements{suffix}:")
        for r in self.requirements:
            lines.append(f"  [{r.verdict.value:<11}] {r.key:<9} {r.title}")
            lines.append(f"      {r.reason}")
            for ev in r.evidence:
                lines.append(f"        - {ev}")

        if self.cases:
            lines.append("")
            lines.append(f"Cases ({len(self.cases)}):")
            for c in self.cases:
                detail = f"  {c.detail}" if c.detail else ""
                lines.append(f"  [{c.outcome:<8}] {c.id:<34}{detail}")

        if self.notes:
            lines.append("")
            lines.append("Notes:")
            for n in self.notes:
                lines.append(f"  - {n}")

        lines.append(bar)
        return "\n".join(lines)
