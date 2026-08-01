---
description: How to debug systematically — reproduce, isolate, fix, verify. Load when a task involves finding and fixing a bug rather than writing new code.
---

# Skill: Systematic debugging

Debugging is not guessing-and-editing. It is a disciplined loop: **reproduce →
isolate → fix → verify**. Follow it; do not skip to a fix you haven't proven.

## 1. Reproduce first

Before theorizing, make the bug happen on demand. Write the **smallest snippet that
triggers it** and run it (with your Python tool, when the code is Python) to see the
*actual* failure — the real exception, wrong value, or stack trace — not the one you
imagine. If you can't reproduce it, you can't confirm any fix; say so and work from
careful static reasoning, lowering confidence.

A bug you can't reproduce is a hypothesis, not a finding.

## 2. Isolate the real cause

Narrow down where it actually breaks. Don't fix the first suspicious line.

- **Print/inspect intermediate state** at the boundaries — inputs, the value just
  before the failure, the branch actually taken.
- **Bisect**: halve the input or the code path and see which half carries the bug.
- **Check one assumption at a time** — the thing you're "sure" about is often the bug
  (an off-by-one, a wrong type, a mutated shared object, an unhandled empty case).
- Distinguish the **symptom** (where it crashes) from the **cause** (why the bad
  value got there). Fixing the symptom usually just moves the bug.

## 3. Fix the root cause, minimally

Make the **smallest change that addresses the actual cause** — not a broad rewrite,
not a try/except that swallows the symptom, not unrelated "while I'm here" edits.
Match the surrounding code's conventions. If there are several reasonable fixes,
prefer the one that's clearest and least likely to introduce new edge cases.

## 4. Verify the fix — and that you didn't break anything

Re-run your reproduction and confirm it now behaves correctly. Then check the
**surrounding behavior** still holds (the fix didn't break the normal path or an
adjacent case) — run a couple of those too. If you could not run the code, state
plainly that the fix is **reasoned but unverified** and lower confidence.

## 5. Explain what and why

Report **what was actually wrong** and **why the fix resolves it** — root cause, not
just a diff. That lets the orchestrator trust the fix and a human learn from it. Note
any assumption you had to make (e.g. about input ranges) and anything you couldn't
verify.

## The honesty rule

Never claim a bug is fixed that you didn't reproduce-and-re-verify. "I believe this
fixes it but couldn't run it" with lower confidence is correct and useful;
"fixed ✓" on an unrun guess is a defect.
