---
description: How to write and run tests and interpret the results. Load when a task asks you to test code, add tests, or confirm something works.
---

# Skill: writing and running tests

- Test BEHAVIOR, not implementation: assert on what the code should produce for
  given inputs, including edge cases (empty, boundary, error paths).
- Run the tests with your tool and read the ACTUAL output — pass/fail, the error,
  the values. Don't assert a test passes without running it.
- A good test is small, deterministic, and names what it checks. Prefer a few sharp
  cases over many shallow ones.
- If a test fails, report the failure honestly and either fix the code or explain
  the discrepancy — never hide a red test.
- State clearly which tests you actually ran and their result; if you couldn't run
  them, say so and lower confidence.
