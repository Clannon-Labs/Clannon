# HANDOFF — feat/c6-consistency-demo

Branch: `feat/c6-consistency-demo`
Purpose: Critical Benchmark 6 + Demo Readiness — multi-agent architectural-consistency
demo scene that invokes the four drift-net checks as subprocesses and renders a
per-surface + per-invariant PASS/FAIL table with a one-line verdict.

---

## Stacked-PR dependency — READ BEFORE MERGING

This branch bundles verbatim copies of files that belong to four still-open PRs.
The copies are byte-identical to their source branches (diffed at review time) and
were included solely to make the demo runnable before those PRs land on main.

| PR  | Files bundled here (verbatim copies)                     |
|-----|----------------------------------------------------------|
| #13 | `backend/tests/expert_contract.py`                       |
| #21 | `backend/tests/registration_drift.py`                    |
| #31 | `backend/tests/benchmarks/sse_contract_drift.py`         |
| #32 | `backend/scripts/check_invariants.py`                    |

**Recommended merge order:**

1. Land PRs #13, #21, #31, and #32 first (in any order — they are independent).
2. Rebase or re-open `feat/c6-consistency-demo` afterward and drop the four bundled
   copies (they will already exist on main from step 1).
3. Merge this branch last.

**Why this matters:**

- *Redundancy after step 1:* once the four PRs are on main, the bundled copies here
  become duplicates. They will clean-merge (identical bytes) but should be pruned
  to avoid two canonical homes for the same file.
- *Silent drift risk:* if any of the four PRs is revised before it merges, this
  branch's frozen copy diverges from the real check — which is precisely the drift
  condition this demo exists to catch. If you notice a revision to #13/#21/#31/#32
  after this PR opens, update the corresponding bundled copy here before landing.

No code in the four checks was modified; this branch is strictly additive.

---

## What was added on this branch

- `backend/scripts/c6_consistency_demo.py` — the demo runner (stdlib-only, no
  backend imports, read-only).
- `backend/tests/test_c6_consistency_demo.py` — unit + integration test coverage
  for the demo (69 tests pass on clean HEAD).
- `backend/tests/expert_contract.py` — verbatim from #13.
- `backend/tests/registration_drift.py` — verbatim from #21.
- `backend/tests/benchmarks/sse_contract_drift.py` — verbatim from #31.
- `backend/scripts/check_invariants.py` — verbatim from #32.

Run from repo root:

    backend/.venv/bin/python backend/scripts/c6_consistency_demo.py
