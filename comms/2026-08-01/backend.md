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

## dispatched workers
- `13:25` **orchestration** worker via **claude** — 2026-08-01_decision-log-events-not-payloads.md — exit 0, 495s — output: `.agents/runs/20260801-131709-orchestration.out`

## answer-loss bug — found by the owner using the product, fixed

Owner asked Clannon what model it is, saw only the say() preamble, and never got
the answer. The answer existed, was correct, and appeared ONLY in the server's
terminal log. Run reported `delivered`.

**Cause** (`api/run_driver.py`, introduced recently in `900e2cc`): chat delivery
gated on `if not run.message or ctx.tool_calls or ctx.expert_calls`. A say()
preamble sets `run.message`; an identity question needs no tool or expert; all
three false, answer dropped. Worse, **`say` is a native tool that does not
register in `ctx.tool_calls`** — the guard checked for evidence of work in a list
the relevant call never appears in.

**Fix:** deliver unless the user has already seen EXACTLY this text.
`already_delivered = bool(run.message) and run.message.strip() == text.strip()`.

**A real trade was hiding here, and it is now explicit.** The suppression existed
to stop a weak model that paraphrases itself posting two near-identical messages.
That case is genuine. The old heuristic could not tell it apart from a preamble +
real answer, and optimised for the cosmetic case at the cost of the catastrophic
one. Policy now: **a duplicated line is cosmetic, a swallowed answer is a broken
product** — when in doubt, deliver. A paraphrasing model may now post two similar
messages; that is the accepted cost, not a new bug.

`tests/message_channel.py::test_chat_with_only_accidental_say_retains_say_as_sole_response`
pinned the OLD policy. Rewritten rather than deleted, with the reasoning in its
docstring, plus a counterpart pinning the one case still suppressed (an exact
duplicate). New file `tests/chat_answer_reaches_the_user.py` — 5 tests including
the owner's exact shape. Mutation-checked: restoring the old guard fails the two
that matter.

**Boundary crossing, declared:** `api/**` is the API specialist's tree and I
edited it directly instead of dispatching, because it was a user-visible
answer-loss bug and the owner asked for a quick fix.

Suite: **1567 passed, 0 failed, 0 skipped** (live Qdrant + ClamAV).

`tests/orchestrator_ports.py::test_memory_store_and_recall_for_user` failed once
mid-session and passes in isolation — the known pre-existing flake. Write
visibility is ruled out (0/4800); `core/memory/hydration.py` ranking remains the
suspect.

## natural-language memory deletion — false success fixed

Owner asked Clannon to remove a learned memory. Run audit proved it never tried:
the first turn called only session `recall`; the deletion turn called only `say`,
then claimed success. No deletion capability existed, and the prompt explicitly
told orchestration not to manage memory.

Fixed with a central-only `forget_memory(memory_id)` command. Manager-selected
context now carries opaque deletion handles for inferred entries. The command
accepts only an id visible in this authenticated turn, then Manager rechecks
ownership and storage. Guessed/foreign/missing ids fail without deletion; Clannon
is explicitly forbidden to claim success unless result is `deleted: true`.
Batches/experts receive no memory port. Wiki remains UI-managed. Curator skips
delete/forget turns so removed content cannot be recreated immediately.

Proof:

- focused: 69 passed, then new seam-specific 19 passed;
- invariant checker: 7 PASS, 1 existing NETWORK-path WARN;
- full backend: **1574 passed**, one existing RestrictedPython warning;
- live disposable-user API + real Haiku: `forget_memory` called, run delivered,
  Qdrant entry absent afterward, success reported; disposable state cleaned.
- `19:52` **security** worker via **codex** — 2026-08-01_identity-filter-inverted.md — exit 0, 807s — output: `.agents/runs/20260801-193904-security.out`

## current time — real tool, real API proof

Owner added `tools/time.py` after Clannon could not answer a simple current-time
question. Hardened it as a deterministic READ tool: UTC default, optional explicit
IANA timezone, aware ISO-8601 output, honest schema/description, invalid-zone failure.

Focused proof: 12 passed. Real API + real model against a disposable user asked for
current Kathmandu time, called `time.current_time`, delivered a complete answer, and
named Kathmandu. Disposable SQLite/Qdrant state cleaned. Full backend: **1579 passed**,
one existing RestrictedPython warning.
