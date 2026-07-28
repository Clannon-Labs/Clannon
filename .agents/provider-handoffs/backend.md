# Shared provider handoff — backend

Transfers live backend-coordinator work between Claude Code and Codex.

**If you are a fresh Codex session: read this whole file, then the boot sequence
at the top of `AGENTS.md`.** Nothing is injected into your session at launch —
`crew.sh start backend --codex` runs plain `codex` in the repo root, so what you
know is exactly what you read. This file is written for that.

---

## THE MENTAL MODEL — read this even if you skip the rest

Durable framing. It does not change week to week, and it is what makes the
detailed docs make sense.

**What Clannon is.** A production monorepo: a Python backend (pipeline →
orchestrator → experts/tools, with memory, security and an API/SSE surface) and a
Next.js frontend. Not a prototype — it is built to production standards
throughout, which is why `LAW/README.md` exists and outranks every other doc.

**Where we are.** V1 is **not done and has never faced a real user.** That single
fact decides most arguments. It is why new work stays in Python (no second
toolchain tax on an unfinished product), why "ship it to users" is a live open
question, and why stability outranks new surface area.

**The bar we are building to.** Six Critical + three Exceptional benchmarks in
`docs/benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md` (the owner's spec of the bar
— it carries no status, deliberately). Honest verdicts live in exactly one place:
`docs/benchmarks/V1_GAP_ANALYSIS.md`. As of 2026-07-28: **CB6 PASS, five
PARTIAL.** The outreach gate is all six Critical passing plus one Exceptional.

**Your role.** You are the **coordinator**, not a labour agent. The owner has
been explicit: *"you are a DICTATOR, not a labor!"* Your context is the scarce
resource. You own `foundation/`, `core/pipeline.py`, `delivery/`, `config/`,
`scripts/`, `docs/`, and final integration + merge authority. You are the **sole
pusher** — specialists commit, you push.

**How work actually gets done.** Five specialists own disjoint trees
(memory, orchestration, security, api, frontend) and coordinate hub-and-spoke
through you, never with each other. You delegate through **headless workers**
(`./scripts/crew.sh run <role> --brief <file> --dir <paths>`), review the diff,
run the suite, and commit. Finding work outside your tree is the START of a task,
not the end of it — file the proposal AND dispatch AND push it. See the
"THAT'S X'S JOB" section in `CLAUDE.md`.

**Messaging is PULL, never push.** Nothing injects into a running session. You
check `comms/<today>/` and `proposals/to-backend/` yourself, at session start and
after each unit of work. **Idle is a legitimate state** — the "never sit idle"
policy is retired and was the most expensive bad instruction we ever followed.

**You are expected to disagree.** Before acting on any instruction — the owner's
included — confirm it actually helps. Say so BEFORE the work, never after as an
excuse. The owner writes their thinking into `drafts/owner_thoughts/` expecting
pushback.

**Honesty is load-bearing.** PARTIAL means PARTIAL. A verdict you cannot
substantiate stays unchanged. Tests never fake a pass. This is LAW 7 and it is
the thing most worth protecting when you are tired or the work "should" have
finished something.

---

## Current checkpoint

- Provider: Codex (interactive backend coordinator)
- Updated: **2026-07-28**
- HEAD: `60504c9`, everything pushed, suite green (1498 passed, 13 skipped —
  qdrant + ClamAV are service-dependent and unavailable on this box; that is
  normal, not a failure).

### What this session did

**1. Reconciled benchmark + phase status with reality** (`b3ed4fb`, `00737ee`).
The status docs had drifted weeks behind the code, which is worse than having
none — agents follow them and work on finished things.
- **CB6 → PASS.** First Critical benchmark to pass. Verified directly, not on a
  worker's report: 8 tests, zero skips, and a deliberately mutated fixture (a
  bogus run_status) IS caught. Frontend tree clean, so the green reproduces from
  committed state.
- CB2/CB4/CB5 held at PARTIAL with named reasons. Only CB6 moved.
- Phases 0/3/4 → `docs/benchmarks/reached/`; phases 1/5 → in progress.
- Fixed a contradiction I had shipped myself: ROADMAP still told memory that CB1
  "needs `valid_at` typing" while the gap analysis in the same commit recorded it
  as landed.
- `reports/INTEGRATION_CONTRACT.md` is now **tracked** (it was gitignored while
  CB6's PASS depended on it existing). Note the mechanism: the pattern had to
  become `reports/*`, because git does not descend into an excluded directory and
  a `!` re-include inside one is silently dead.

**2. Corrected the Integration Contract via a dispatched api worker** (`6d31c52`).
It claimed exception/cancellation bypasses audit derivation; `run_driver.py:488`'s
`finally` covers every terminal status. Documented the real limitation instead
(incomplete `participants` on the crash path, `run_driver.py:498-505`) — still an
open CB4 gap.

**3. Tidied `reports/`** (`dbd8a31`). One folder per role, coordinator included —
`reports/backend/` now holds report_v1..v18, which had been sitting loose at the
root.

**4. Rewrote `DECISIONS_FOR_OWNER.md`** (`9a75de1`). New rule from the owner: **a
decision file outside `reports/archived_owner_replies/` MEANS the owner must
decide it.** If they need not act, it does not belong outside. The old docket
mixed real decisions, tracking notes, and history — and omitted the three
decisions that actually gate work.

**5. Fixed `crew.sh` leaking its lock.** The EXIT trap was single-quoted, so
`$lock` expanded after the function returned and `local lock` was gone; under
`set -u` it aborted and the trap never fired. Symptom was only a stray error line
after successful runs, because a stale lock self-heals.

**6. Ran first existing-system hardening tranche** (`0b40607`, `13686e3`,
`60504c9`).
- CB5 moved honestly to PASS: deterministic verifier detects all 8 adversarial
  benchmark classes; 5 benign controls stay clean. Outreach: 2 Critical PASS,
  4 PARTIAL.
- API cancellation/exception audit now preserves authoritative participants;
  foreign/unknown decision-run IDs share non-disclosing 404 proof.
- Same user/mission/expert workspace calls serialize restore → run → snapshot;
  unrelated keys stay concurrent; failure releases locks; idle locks disappear.
- Law-2 cleanup split workspace transactions and API source projection:
  production files now 481/41 and 498/39 lines.
- Central-config inventory reconciled: D1–D12 settled, Phase 3 substantially
  wired, D5 model centralization is next safe engineering work.
- Worker identities/routing corrected (`2f91e89`): backend-worker proposals go
  to `proposals/to-backend/from_workers/`; specialist workers use
  `<role>-worker` → `backend-coordinator` in `to-backend/`; dispatch briefs now
  live under `.agents/briefs/<role>/`.
- Three full suites passed during integration; latest: 1498 passed, 13 skipped.

### What is open, and who owns it

- **Owner-gated (do NOT start these):** four items in
  `reports/DECISIONS_FOR_OWNER.md` — Rust design discussion, real model+infra
  prices/final budget go-live, whether V1 ships to users, and archive-cap
  divergence. Batch is greenlit and no longer on docket.
- **Benchmark work** is per-specialist and listed in `docs/ROADMAP.md` §2/§4.
- **Known stale:** `docs/RESUME.md` config snapshot; current truth is
  `docs/config/CONFIG_INVENTORY.md`.

### Traps this session actually hit — do not relearn them

- **A targeted test run is not a suite run.** A loop-guard change touching
  `run_agent` broke CI because I verified with 7 files. Run the full suite before
  every commit; it takes ~3.5 minutes and the OOM norm that once justified
  skipping it no longer applies.
- **Section-boundary replaces eat content between anchors.** One deleted four
  numbered steps from `RUST_MIGRATION_STRATEGY.md` while leaving the heading.
  Re-read the rendered file after any structural edit.
- **A worker's summary is not verification.** Check its claims against source and
  cite `file:line`. Two workers this week were correct; one was killed before
  writing anything and its "conclusions" existed only in a log.
- **Fixing a config does not fix a session already running under it.** The
  release agent looked broken; its Codex session had simply booted under the old
  `.codex/config.toml` sandbox.
- **Never sweep another agent's files.** Always `git commit -- <explicit paths>`.
  The tree is shared and frontend/release files are routinely dirty.

## Change note

Updated 2026-07-28 after first hardening tranche. Previous checkpoint below
describes status-reconciliation and crew-workflow work that remains valid
history; current checkpoint supersedes its CB5/crash-participant/batch-gate
claims.

Rewritten 2026-07-28 to add the MENTAL MODEL section at the top, on the owner's
instruction: Claude's weekly usage limit is nearly exhausted, so the backend role
will run on Codex, and a fresh Codex session must acquire the long-term picture
from files alone. The previous checkpoint documented the crew-workflow rewrite;
that work is done and canonical in `docs/architecture/CREW_WORKFLOW.md`.

Two claims in the previous checkpoint are now **obsolete**: the CB4 decision-mirror
gap (cancelled/crashed runs writing zero records) is FIXED, and the frontend's
uncommitted WIP has been committed — the tree is clean there.

## Previous checkpoint (2026-07-27)

- Provider: Claude Code (standalone, not in tmux)
- Task: **DONE — full crew-workflow redesign**, on the owner's instruction to
  rebuild from scratch rather than bolt fixes on a weak base. Canonical result:
  **`docs/architecture/CREW_WORKFLOW.md`**, which supersedes every older
  description of agent coordination.
- What changed:
  - **All push-based messaging deleted.** systemd wake path units + heartbeat
    timers disabled, unenabled, and removed from `~/.config/systemd/user/` AND
    the repo (the standup script silently reinstalled them; it is gone too).
  - **Seven scripts deleted, replaced by one: `scripts/crew.sh`**
    (`start|status|attach|stop|run`). No send-keys anywhere in it.
  - **New tracked channel `comms/YYYY-MM-DD/<role>.md`** — one file per role per
    day, sharded so concurrent appends cannot clobber.
  - **No automatic provider failover.** Provider chosen at launch.
  - **"Never sits idle" RETIRED** — the most expensive bad instruction we ever
    followed (busywork, git churn, agents trampling each other).
  - **Challenge-the-owner mandate added** to `CLAUDE.md` + `AGENTS.md`.
- Verification: `crew.sh` syntax-checked and smoke-tested with no live agents.
  No backend/ or frontend/ source touched by that pass.
