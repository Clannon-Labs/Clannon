---
description: How to debug systematically — reproduce, isolate, fix, verify. Load when a task involves finding and fixing a bug rather than writing new code.
---

# Skill: systematic debugging

- REPRODUCE the bug first. Write the smallest snippet that triggers it and run it
  with your tool to see the actual failure, rather than reasoning in the abstract.
- ISOLATE: narrow where it breaks — print intermediate values, bisect the input, or
  check one assumption at a time. Find the real cause, not a symptom.
- FIX the root cause with the smallest change that addresses it; don't paper over it
  or rewrite unrelated code.
- VERIFY: re-run the reproduction and confirm it now passes, and check you didn't
  break the surrounding behavior. If you couldn't run it, say the fix is unverified.
- Explain WHAT was wrong and WHY the fix works, not just the diff.
