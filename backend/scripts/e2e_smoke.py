"""
End-to-end smoke harness for the Vraksha pipeline.

Runs real turns through `core.pipeline.run` (the single end-to-end runner) and
checks the outcomes, with every trace going to the unified log file. Routes on the
models.yaml defaults (Anthropic for everything except grounded search), so it does
not lean on Gemini's rate-limited free tier.

    cd backend && PYTHONPATH=. .venv/bin/python scripts/e2e_smoke.py
    ...                                          scripts/e2e_smoke.py --case qa
    ...                                          scripts/e2e_smoke.py --list

Cases:
  qa            full pipeline, direct-knowledge answer (no tools)
  layers-off    drop sanitizer + normalizer + verifier — proves layer independence
                (the orchestrator answers raw, unsanitized, unverified input)
  filter-off    drop the output filter — delivery still ships the draft
  code          code expert path (exercises a tool-driving expert)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv(".env")
load_dotenv(".env.local", override=True)
if os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_API_KEY"):
    os.environ.pop("GEMINI_API_KEY", None)

from observability import DecisionLogSink, configure_logging  # noqa: E402
from core import pipeline  # noqa: E402
from core.budget.context import budget_exempt_scope  # noqa: E402


def _stages_without(*names: str):
    """ACTIVE_STAGES minus the named layers — used to prove a layer can be dropped."""
    drop = set(names)
    return [s for s in pipeline.ACTIVE_STAGES if s.name not in drop]


async def _run(brief: str, *, session: str, stages=None) -> "object":
    sink = DecisionLogSink()
    # Smoke runs are outside any api/ turn (no usage_scope either) — explicit opt-out so the
    # budget anchor skips quietly instead of logging a wiring-bug ERROR once enforcement is on.
    with budget_exempt_scope():
        return await pipeline.run(
            brief, session_id=session, user_id="smoke-user",
            decision_log=sink, stages=stages,
        )


def _check(flow, *, expect_answer: bool = True) -> tuple[bool, str]:
    summary = flow.summary()
    answer = getattr(flow.ctx, "final_response", None) or (
        flow.ctx.orchestrator_response.text if flow.ctx.orchestrator_response else None
    )
    if flow.should_stop:
        return (not expect_answer, f"stopped at {summary.get('stage')}: {summary.get('reason') or summary.get('error')}")
    if expect_answer and not answer:
        return (False, "delivered but no answer text")
    return (True, f"answer={str(answer)[:90]!r}")


# ---- cases ----------------------------------------------------------------

async def case_qa() -> tuple[bool, str]:
    flow = await _run(
        "In one sentence, what is a hash map and why is lookup O(1) on average?",
        session="smoke-qa",
    )
    return _check(flow)


async def case_layers_off() -> tuple[bool, str]:
    # no sanitizer, no normalizer, no verifier — orchestrator must still answer
    flow = await _run(
        "In one sentence, what is tail recursion?",
        session="smoke-layers-off",
        stages=_stages_without("sanitizer", "normalizer", "verifier"),
    )
    return _check(flow)


async def case_filter_off() -> tuple[bool, str]:
    flow = await _run(
        "In one sentence, what is a race condition?",
        session="smoke-filter-off",
        stages=_stages_without("filter"),
    )
    return _check(flow)


async def case_code() -> tuple[bool, str]:
    flow = await _run(
        "Write a Python function is_palindrome(s) that ignores case and spaces, "
        "then briefly confirm it works on 'A man a plan a canal Panama'.",
        session="smoke-code",
    )
    return _check(flow)


CASES = {
    "qa": case_qa,
    "layers-off": case_layers_off,
    "filter-off": case_filter_off,
    "code": case_code,
}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=sorted(CASES) + ["all"], default="all")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    if args.list:
        print("cases:", ", ".join(sorted(CASES)))
        return 0

    log = configure_logging(console=False)
    print(f"# unified log -> {log}\n")

    selected = sorted(CASES) if args.case == "all" else [args.case]
    results: list[tuple[str, bool, str]] = []
    for name in selected:
        print(f"--- case: {name} ---", flush=True)
        try:
            ok, detail = await CASES[name]()
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, f"raised {type(exc).__name__}: {exc}"
        results.append((name, ok, detail))
        print(f"    {'PASS' if ok else 'FAIL'} — {detail}\n", flush=True)

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"=== {passed}/{len(results)} passed ===")
    for name, ok, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
