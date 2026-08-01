---
description: How to write and run tests and interpret the results. Load when a task asks you to test code, add tests, or confirm something works.
---

# Skill: Writing and running tests

A test exists to **catch a wrong answer** and to let you (and the orchestrator) trust
that code does what it claims. Write tests that could actually fail, run them, and
read the real result.

## 1. Test behavior, not implementation

Assert on **what the code should produce** for given inputs — the observable
contract — not on internal steps. Implementation-coupled tests pass for the wrong
reasons and break on harmless refactors. Pin the input, pin the expected output,
compare.

## 2. Cover the cases that actually break code

A few sharp cases beat many shallow ones. Deliberately include:

- **The normal case** — a representative valid input.
- **Edges** — empty input, a single element, the boundary value (0, 1, max), the
  largest/smallest realistic input.
- **Error paths** — invalid input that should raise or be rejected; assert it
  actually does.
- **The specific case from the task** — if the request named example inputs/outputs,
  test exactly those.

## 3. Actually run them and read the output

Run the tests with your Python tool and **read the real result** — pass/fail, the
assertion that failed, the actual vs expected values, the traceback. **Print what you
need to see** (only printed output comes back). Never assert "tests pass" without
having run them; an unrun test proves nothing.

## 4. A good test is small, deterministic, named

Each test checks one thing, has a name that says what it checks, and gives the same
result every run (no reliance on time, randomness, network, or external state). If
something is nondeterministic, control it (seed, fixed input) or don't assert on it.

## 5. Report results honestly

If a test fails, **say so** — then either fix the code and re-run, or explain the
discrepancy if the test itself was wrong. Never hide or delete a red test to make
the output look clean. State clearly **which tests you actually ran and their
result**; if you couldn't run them (non-Python code, execution unavailable), say the
tests are written-but-unrun and lower confidence.

## The honesty rule

"Verified by these tests, here's the output" (with the run shown) is the goal.
"Should work" on tests you never executed is not verification — mark it unverified.
