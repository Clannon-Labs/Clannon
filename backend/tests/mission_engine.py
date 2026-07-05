"""
Tests for the Mission Engine's ungated core (core/orchestrator/mission.py) --
the fail-closed completion gate and the mission budget pre-check. Design ref:
proposals/archive/to-backend/2026-07-05_mission-engine-design-v2.md §4/§7.

Acceptance matrix:
  (a) evaluate_completion: every criterion met -> DONE
  (b) evaluate_completion: one criterion unmet -> PROPOSED_COMPLETE
  (c) evaluate_completion: verdict count != criteria count -> PROPOSED_COMPLETE
      (fail-closed on a judgment that dropped or added a criterion)
  (d) evaluate_completion: description mismatch at a position (a reordered or
      malformed judgment) -> PROPOSED_COMPLETE even when every `met` is True --
      proves position correlation is integrity-checked, not blindly trusted
  (e) evaluate_completion: zero criteria + zero verdicts -> DONE (the vacuous
      case falls out of the same length/met checks, pinned explicitly)
  (f) budget_is_sufficient: both ceilings cover the estimate -> True
  (g) budget_is_sufficient: mission ceiling insufficient -> False regardless of
      how large the user ceiling is
  (h) budget_is_sufficient: user ceiling insufficient -> False regardless of
      the mission ceiling
  (i) budget_is_sufficient: no mission ceiling set (mission_remaining is None)
      -> only the user ceiling gates
"""

from __future__ import annotations

from foundation import TokenBudget

from core.orchestrator.mission import (
    CompletionJudgment,
    Criterion,
    CriterionVerdict,
    MissionStatus,
    budget_is_sufficient,
    evaluate_completion,
)


def _criteria(*descriptions: str) -> list[Criterion]:
    return [Criterion(description=d) for d in descriptions]


def _verdicts(*pairs: tuple[str, bool]) -> CompletionJudgment:
    return CompletionJudgment(
        criteria_verdicts=[CriterionVerdict(description=d, met=m) for d, m in pairs]
    )


# ─── (a) every criterion met -> DONE ────────────────────────────────────────

def test_all_criteria_met_advances_to_done():
    criteria = _criteria("ships the report", "tests pass")
    judgment = _verdicts(("ships the report", True), ("tests pass", True))
    assert evaluate_completion(criteria, judgment) == MissionStatus.DONE


# ─── (b) one unmet criterion holds at proposed_complete ────────────────────

def test_one_unmet_criterion_holds_proposed_complete():
    criteria = _criteria("ships the report", "tests pass")
    judgment = _verdicts(("ships the report", True), ("tests pass", False))
    assert evaluate_completion(criteria, judgment) == MissionStatus.PROPOSED_COMPLETE


# ─── (c) length mismatch fails closed ───────────────────────────────────────

def test_fewer_verdicts_than_criteria_fails_closed():
    criteria = _criteria("ships the report", "tests pass")
    judgment = _verdicts(("ships the report", True))
    assert evaluate_completion(criteria, judgment) == MissionStatus.PROPOSED_COMPLETE


def test_more_verdicts_than_criteria_fails_closed():
    criteria = _criteria("ships the report")
    judgment = _verdicts(("ships the report", True), ("extra one", True))
    assert evaluate_completion(criteria, judgment) == MissionStatus.PROPOSED_COMPLETE


# ─── (d) description mismatch (reordered/malformed judgment) fails closed ──

def test_reordered_verdicts_fail_closed_even_if_all_met():
    criteria = _criteria("ships the report", "tests pass")
    # Same set of descriptions, swapped order relative to `criteria` -- every
    # `met` is True, but position i's description no longer matches criteria[i].
    judgment = _verdicts(("tests pass", True), ("ships the report", True))
    assert evaluate_completion(criteria, judgment) == MissionStatus.PROPOSED_COMPLETE


def test_paraphrased_description_fails_closed():
    criteria = _criteria("ships the report")
    judgment = _verdicts(("the report ships", True))
    assert evaluate_completion(criteria, judgment) == MissionStatus.PROPOSED_COMPLETE


# ─── (e) vacuous zero-criteria case ─────────────────────────────────────────

def test_zero_criteria_and_zero_verdicts_advances_to_done():
    assert evaluate_completion([], CompletionJudgment()) == MissionStatus.DONE


# ─── (f)-(i) budget pre-check ───────────────────────────────────────────────

def test_budget_sufficient_when_both_ceilings_cover_estimate():
    budget = TokenBudget(user_remaining=1000, mission_remaining=500)
    assert budget_is_sufficient(budget, 100) is True


def test_budget_insufficient_when_mission_ceiling_too_low():
    budget = TokenBudget(user_remaining=1_000_000, mission_remaining=50)
    assert budget_is_sufficient(budget, 100) is False


def test_budget_insufficient_when_user_ceiling_too_low():
    budget = TokenBudget(user_remaining=50, mission_remaining=1_000_000)
    assert budget_is_sufficient(budget, 100) is False


def test_budget_sufficient_with_no_mission_ceiling_set():
    budget = TokenBudget(user_remaining=1000, mission_remaining=None)
    assert budget_is_sufficient(budget, 999) is True
    assert budget_is_sufficient(budget, 1001) is False
