# ROADMAP — what we're building, and who's on what

**Read this first when you need to know "what should I work on?"** It is the
single entry point; the detailed plans it points at stay authoritative for their
own areas.

Last reconciled: **2026-07-28**, after owner proposal sweep.

> **Standing rule:** if you finish your lane and nothing here is assigned to you,
> **that is a valid state.** Write your handoff and stop. Do not invent work
> (`docs/architecture/CREW_WORKFLOW.md` §2.2).

---

## 0. Where the detail lives

| Source | Covers | Trust it? |
|---|---|---|
| **this file** | cross-role priorities, the Rust track, who owns what | current |
| `docs/benchmarks/V1_GAP_ANALYSIS.md` | per-benchmark honest verdicts | current — reconciled 2026-07-28 |
| `docs/benchmarks/mission/` | the V1 Premium-Parity phase plan | current — reconciled 2026-07-28; backend-only |
| `docs/architecture/RUST_MIGRATION_STRATEGY.md` | how any Rust work happens | current, canonical |
| `docs/architecture/CREW_WORKFLOW.md` | how agents coordinate | current, canonical |
| `LAW/README.md` | the seven laws | current, canonical |

## 1. The two tracks

We are running **two tracks at once**, deliberately:

**Track A — finish V1 (Python).** The product still has to work. V1 is not done
and has no real-user feedback yet. Owner is arranging a small friends/family
cohort in parallel; engineering keeps closing capability gaps and does not wait
on that outreach.

**Track B — Rust, by addition only.** An experiment run alongside components
that already work; nothing is rewritten for its own sake, and new work stays
Python. See §3. **Nothing has started** — owner deferred it while Python V1
advances.

Track A does not pause for Track B. If they ever conflict, **Track A wins** —
shipping a working product beats architectural progress.

## 2. Track A — V1 capability

**Shipped since v0.2.0** (gap-analysis verdicts reconciled 2026-07-28):

- **CB6 — multi-agent consistency → PASS.** The only Critical benchmark that
  passes. `reports/INTEGRATION_CONTRACT.md` exists; the SSE contract-drift
  benchmark is green and enforcing.
- **CB5 — security validation**: earned-seal state flows end-to-end; prevent,
  classify, explain and audit are honestly proven. **Stays PARTIAL** — a PASS
  was claimed on 2026-07-28 and **reverted the same day** after an independent
  check. The new pre-screen rules match the battery's exact wording; the same
  attack intent reworded still evades, and the three C5-native families are not
  in the live regression at all. Fitting rules to fixture text is not detection.
- **CB4 — institutional decision memory**: durable mirror + `GET /runs/:id/decisions`,
  covering every terminal outcome including cancelled/crashed. Stays PARTIAL —
  tradeoffs are flat prose and benchmark ADR participant provenance is absent.
- **CB2 — large repo understanding**: symbol tier, AST search, dep-graph
  traversal, archive ingestion, cross-call workspace persistence. Stays
  PARTIAL — architectural explanation is NOT-YET.

Outreach gate = all 6 Critical PASS + ≥1 Exceptional. Today: **1 PASS, 5
PARTIAL.**

**Open, in rough priority order:**

1. **CB3 / EB3 — real media ingestion.** Mechanism proven, actual multi-modal
   ingestion absent. Owner: memory (extractor) + orchestration (experts).
2. **CB1 / EB1 — temporal truth.** `fact|assumption` + `valid_at` typing has
   **landed**. Manager-owned tier curation plus save-time rationale/saver/session/
   trace/participant provenance and real archive visibility landed 2026-07-30.
   What remains: retrieval explanation (why an item was selected), complete
   author/RFC linkage, and explicit supersession linkage so current-vs-historical
   is a relationship, not prose. Owner: memory.
3. **Harden existing foundations, then build batch architecture.** Owner
   greenlit Redis-budget and batch foundations on 2026-07-28. Build is no
   longer decision-gated, but remains stability-first and propose-first: prove
   Redis money safety, then Mission Engine, bounded cross-batch awareness,
   and one batch end-to-end.
4. **Prompt depth pass (owner-ratified 2026-07-31).** Owner ruled: much longer,
   far more detailed system prompts following their guide
   (`Vault/projects/System_prompt_style_guides/PROPMT_TO_GET_INTELLIGENCE_LIKE_CLAUDE-FABLE-5.md`
   — read its OUTLINE, it is 123KB). Structure is READY: per-batch prompt
   directories landed 2026-07-31. Order: **memory read/write prompts first** (the
   memory system prompt is 39 lines, while the secure overlay took filter to 518
   and verifier to 219 — the moat has the thinnest prompt in the system), then the
   central orchestrator, then experts and batch orchestrators. Owner: backend +
   memory + orchestration.
5. **Memory read-side LLM (owner-ratified 2026-07-31).** Keep vector search; add a
   lightweight LLM that retrieves exactly what the orchestrator needs. It must
   reach memory ONLY through powerful, precise tools — it must not be able to open
   and read memory directly. That constraint is also what keeps tenant isolation
   enforceable. Owner: memory.
6. **Guard false positives (owner-ratified 2026-07-31, option 1 only).** Cut false
   positives by making the guards MORE DISCRIMINATING — better examples, sharper
   instructions per the guide. **NOT by lowering the bar**: owner chose this
   explicitly over compromising detection. `verifier`/`filter` are `locked: true`
   and CB5 is PARTIAL *because detection already evades on paraphrase*, so any
   change runs against `tests/benchmarks/cb5_verdict_honesty.py`. Owner: security.
7. **Budget enforcement go-live.** Code is built but ships
   `enforcement_enabled=False`. Owner supplied provider-pricing references;
   backend must verify them against official current prices, represent
   tier/modality differences honestly, measure conservative infrastructure
   cost, seed production budgets, prove recovery/concurrency, and obtain
   security review. Loader stays fail-closed. Create a fresh owner go-live
   proposal only when those engineering gates are green. Owner: backend.

**Known limitations carried into v0.3.0** (documented, not hidden): one dev-only
Dependabot residual.

## 3. Track B — Rust

**The rule, in two halves. Both matter:**

### 3a. New code → Python

**New work is written in Python. Including new infrastructure.** V1 is not done
and has never faced a user; a second toolchain per new component is a tax we do
not pay yet.

An earlier version of this section said the opposite ("new infrastructural code
prefers Rust"). It was wrong and it contradicted §3b: **parallel implementation
with deferred cutover requires an existing implementation to validate against.**
New code has no Python counterpart and no reference behaviour, so writing it in
Rust is a different strategy — greenfield, no safety net — not the one we chose.

**Stays TypeScript:** the whole frontend. Not up for discussion right now.

If a new component genuinely needs Rust-level guarantees Python cannot give,
that is a **proposal with a specific argument** — never a default. Revisit this
after V1 ships.

### 3b. Existing code → port only by addition

Governed by `docs/architecture/RUST_MIGRATION_STRATEGY.md`: write the Rust 1:1
alongside the Python, keep Python live, cut over at the port boundary only when
proven, keep Python as a time-boxed fallback, then delete it.

**Never a big-bang rewrite.** Declining a rewrite must mean "wouldn't improve
it," never "too risky to try" (LAW 6).

**Hard prerequisite before ANY port:** the component's tests must be able to
validate either language — driven through the port, not through Python
internals. Today's pytest imports Python modules directly and cannot validate a
Rust implementation, so this is real work, not a formality.

**Sequencing:** small / off / boundary-clean first. `foundation/` **last**
(209 in-process importers = FFI on the hottest path for the whole migration).

**Agreed pilot: the Redis budget broker** (`core/budget/`) — port ratified,
~485 lines, off in production, zero ML, already has a process boundary.

**Status: deferred, not started.** Owner settled the general boundary on
2026-07-28: stateful/system components use a separate supervised process with a
versioned API; FFI is only for bounded pure computation where profiling
justifies it. Component-specific conformance, failure, dev, and deploy design
remains required. Python V1 advances first; Rust starts only from a specific
benefit-backed proposal.

## 4. Lanes by role

| Role | Current lane |
|---|---|
| **backend** (coordinator) | existing-system hardening; Redis-budget design/review; foundation/config seams; review + integrate + push; dispatch workers |
| **memory** | CB3/EB3 media ingestion; CB1/EB1 retrieval explanation + author/RFC provenance + supersession linkage (Manager-only curation/save provenance DONE) |
| **orchestration** | central/batch prompt contracts landed; continue Mission Engine + batch hardening, propose-first where owner-gated |
| **security** | standing invariant review of budget/batch designs; widen adversarial regression coverage when new classes appear |
| **api** | remaining run-lifecycle proof areas (cross-user non-disclosure sweep) |
| **frontend** | its own backlog; `HANDOFF.md` in `frontend/` |
| **release** | post-v0.3.0 housekeeping; next release when there is scope |

## 5. Needs the owner, not us

**No actionable owner decision is open.** `proposals/to-owner/` is empty after
the 2026-07-28 rulings:

- shared 50 MiB upload/archive cap plus bomb guards ratified;
- Python capability work continues while owner recruits a small real-user
  cohort in parallel;
- Rust Track B deferred; separate-process/FFI boundary settled;
- official model-price verification and infrastructure measurement assigned to
  engineering. Final budget-enforcement go-live remains owner authority, but no
  proposal is created until engineering gates are green.

This section and `proposals/to-owner/` must agree. New owner proposal means
owner can act now; future gates stay in their engineering plan until ready.

## 6. Stale things worth fixing

Nothing currently known-stale.

Fixed 2026-07-28: `docs/RESUME.md`'s duplicated config snapshot. It named the
ORCHESTRATOR_*/EXPERT_*/TOOL_* constant removal as next work; those constants no
longer exist. It now points at `docs/config/CONFIG_INVENTORY.md` instead of
carrying a second copy of the status — the duplication was the actual defect, so
re-syncing it would only have reset the clock on the same rot.

Fixed 2026-07-28: terminal decision-audit coverage. `run_driver.py`'s `finally`
covers every terminal status and now retains authoritative pipeline context
during cancellation/exception, so recorded expert/tool participants survive
those paths. Focused lifecycle/auth proof: 44 passed.

Fixed 2026-07-28: concurrent same-user/mission/expert workspace calls now hold a
shared keyed transaction across restore → expert run → snapshot. Different
mission/expert keys stay concurrent; cancellation/exception releases locks;
idle keys are removed. Focused orchestration proof: 16 passed.

Fixed 2026-07-28: `V1_GAP_ANALYSIS.md` verdicts + priority stars, and the
`mission/` phase statuses, are reconciled against what actually shipped. Keep
them that way in the same commit as the work (`CLAUDE.md` § keep status
current).

Fixed 2026-07-28: ClamAV refusal, reset, timeout, and broken-pipe transport
failures now normalize to a safe fail-closed `SanitizationError`; programmer
errors remain visible. Hermetic adapter-boundary regressions live in the normal
backend suite.

Fixed 2026-07-28: live-Qdrant full-suite order dependence. Two memory tests
leaked module globals: concurrency retained a fake client/collection state, and
the supersession fault test retained an open breaker. Both now restore exact
prior state through pytest teardown. Full isolated live-Qdrant suite:
1518 passed, 1 existing ClamAV skip.
