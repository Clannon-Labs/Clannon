# Backend coordinator — 2026-08-10

## Redis reconciliation stays in its granting billing period

Audit found a money-safety defect in the off-by-default Redis broker: `reserve()`
used one period, but `reconcile()` asked the clock again. A call crossing a billing
boundary therefore refunded or charged the new period instead of the period that
granted its hold.

`BudgetReservation` now carries the granting period. Redis reconciliation refuses an
unpinned/malformed handle instead of guessing. Regression failed against old code and
proves both balances; focused budget/foundation/anchor suite: 57 passed. Full backend:
1676 passed, 13 dependency skips, 7 subtests.

Enforcement remains OFF. Go-live still needs Redis seeding/broker construction wired
to API billing's fixed anniversary periods, durable failed-reconcile true-up, exact
pricing, infrastructure calibration, security review, and owner approval.
