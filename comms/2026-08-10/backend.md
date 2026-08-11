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

## Independent backend security auditor

Created `backend-audit`, separate from security implementer. Source/`.git`/charters
are Bubblewrap read-only; only auditor outputs writable. Role threat-models and traces
real attacker/control-bypass paths, including conditional and composed design flaws;
static scans are supporting evidence. Codex Security + isolated pinned scanners ready.
Boundary proof passed; launcher proof: 5 tests + 8 role subtests. Baseline not run yet.

Frontend audit design requested through `proposals/to-frontend/`; frontend owns its
domain threat model, coordinator owns root sandbox wiring.

## `backend-audit` now runs on Claude Code too — and the sandbox had no DNS

The auditor was Codex-only; `crew.sh start backend-audit --claude` now works through
the SAME launcher (`backend-audit-sandbox.sh {start|resume|self-test}
[--codex|--claude]`). One script on purpose: the Bubblewrap mount policy is the
boundary, and a per-provider copy would drift.

Found while proving it: `/etc/resolv.conf` symlinks into `/run`, which was never
mounted, so **name resolution failed inside the sandbox on BOTH providers** — the
auditor would have retried its own API forever. The write-boundary self-test passed
throughout, because it only asked about writes. Fixed; `self-test` now fails closed on
resolution, scanner visibility, and provider startup.

Claude equipment is repo-local and tracked, not a marketplace plugin (those hook
edit/commit events this role never performs, or need vendor accounts):
`backend-audit/.claude/` — deny rules, `attack-path-tracer` and `counterevidence`
subagents, `audit-scanners` skill. Detail + what is NOT proven:
`reports/backend/report_v24.md`.

Baseline audit still not run — this is equipment, not a verdict.

Follow-up, same day: measured the auditor's deny rules instead of trusting them. Deny
patterns match a command's LEADING words, so `Bash(semgrep --autofix:*)` would never
have fired against a real `semgrep scan … --autofix` — removed rather than left reading
as enforced. Everything else held: `pip install` / `git commit` / `gh` / `detect-secrets
audit` denied, deny beats an inherited allow rule, `pip-audit` and read-only
`git status` still run.

Owner call: `backend-audit` no longer carries its own provider default. Every role is
Claude unless launched with `--codex`, auditor included. `scripts/instruction.md` now
documents the role — what the sandbox actually does, the self-test, and where findings
land.

Frontend's audit charter answered and archived. Root wiring for `frontend-audit` is
mine, queued not started — and it will NOT be a mirror of the backend sandbox script:
the mount policy is the boundary, so the launcher gets a role parameter the way it
already takes a provider one. Their open question about a Codex default is moot now
that every role defaults to Claude. Asked them for pinned npm audit tooling; not
blocking.

## Independent frontend security auditor ready

Completed interrupted root wiring. `frontend-audit` now has durable Claude/Codex
charters, provider equipment, continuity, routed findings, isolated exact Python/npm
tool locks, and the same role-parameterized Bubblewrap boundary as `backend-audit`.
No frontend source, manifest, lockfile, or project dependency changed.

Boundary proof passed on Claude and Codex: source/`.git`/charters/project dependencies
rejected writes; exact tools ran full ESLint and `tsc --noEmit`, Vitest/Playwright
discovery, and report-only npm audit against real project. Baseline assignment queued;
no candidate risk promoted to finding and no security verdict exists yet. Launcher:
11 passed. Full backend: 1683 passed, 13 service skips, 9 subtests.

## dispatched workers
- `21:59` **frontend** worker via **claude** — 2026-08-10_remediate_frontend_audit_v1.md — exit 1, 22s — output: `.agents/runs/20260810-215910-frontend.out`
- `22:21` **frontend** worker via **codex** — 2026-08-10_remediate_frontend_audit_v1.md — exit 0, 1302s — output: `.agents/runs/20260810-220011-frontend.out`
- `22:25` **orchestration** worker via **codex** — 2026-08-10_disable-alpha-outbound-mutation.md — exit 0, 186s — output: `.agents/runs/20260810-222252-orchestration.out`
- `22:26` **orchestration** worker via **codex** — 2026-08-10_disable-alpha-outbound-mutation.md — exit 1, 4s — output: `.agents/runs/20260810-222619-orchestration.out`
- `22:28` **api** worker via **codex** — 2026-08-10_canonical-mode-mail-preflight.md — exit 0, 352s — output: `.agents/runs/20260810-222251-api.out`
- `22:29` **security** worker via **codex** — 2026-08-10_canonical-production-yara.md — exit 0, 392s — output: `.agents/runs/20260810-222251-security.out`
