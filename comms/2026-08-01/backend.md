# backend — 2026-08-01

## identity leak diagnosed — the FILTER, not the orchestrator

Owner reported Clannon answering "I'm Claude, made by Anthropic". Root cause found
and it is the opposite of where it looked:

- `prompts/orchestrator/system.md:12` already forbids naming an underlying model,
  with the model answer at `:220`. The first draft OBEYED it and said "I'm Clannon,
  built by Clannon Labs. I'm not based on GPT, Claude, Gemini...".
- `prompts.secure/filter/system.md:14-19` BLOCKED that draft, because the rule
  matches on MENTION not CLAIM — the denial names the models in order to deny them.
- The same rule says "made by any other company except Clannon Labs ... allow it",
  which literally permits "made by Anthropic". So the revision that leaked passed.

Filter punished the true answer, then approved the leak. Not a hallucination — the
model was corrected INTO it.

Filed `proposals/to-security/2026-08-01_identity-filter-inverted.md`. The DELIVERABLE
is a bidirectional regression test (denial must pass, leak must block, must fail if
either regresses), not just a wording change — a prompt fix with no test will drift.

**Owner's issue 1 (decision-log text absent from chat) is WORKING AS DESIGNED**: those
were filter-REJECTED drafts, and a rejected draft must never reach the user. Real UX
gap underneath though — `say` announced "let me give you a straight answer" and then
nothing followed.

## end-to-end verification (2026-07-31 late)

- **Media: WORKS.** Real upload path (`scan_upload` -> `ctx.input_files` as
  `run_driver._prepare` seeds it) -> `media.analyst` described the logo correctly.
- **Missions: built + offered, model does not reach for them.** `wiring.py:39-40`
  passes graph AND budget, which is what gates `start_mission`. On an explicit
  "track this as a multi-step project" prompt the model made 42 tool calls, nearly
  all repeated web searches, never opened a mission, hit the wall clock, and
  degraded honestly. System gap, not model failure — evidence for the prompt-depth
  pass. Also explains the owner's token concern: 42 tool calls = 42 LLM turns.

**Four of my own findings yesterday were harness artifacts, not product bugs** (see
2026-07-31 comms). The pattern: I tested a system I assembled instead of the one that
ships. A direct `pipeline.run()` skips `core/warmup.py`; raw bytes as `raw_input` is
not how uploads travel.

## survives independently, worth fixing before a tester arrives

- `security/sanitizers/runner.py` — `flow.fail(result, Origin.SANITIZER)` with an
  exception from `gather(return_exceptions=True)`. `str(asyncio.TimeoutError())` is
  `''`, so a fail-closed security gate records NO reason anywhere.
- Cold text sanitize measured **10.1s** against `sanitizer_timeout_worker_s: 10.0`.
  Production survives only because a best-effort warmup wins the race; if that
  warmup times out it logs a warning and continues, and the first real request dies
  with the blank error above.
