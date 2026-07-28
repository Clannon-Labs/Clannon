# ROADMAP — what we're building, and who's on what

**Read this first when you need to know "what should I work on?"** It is the
single entry point; the detailed plans it points at stay authoritative for their
own areas.

Last reconciled: **2026-07-27**, just after `v0.3.0`.

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
and has never faced a real user. This track keeps shipping in Python.

**Track B — Rust, by addition only.** An experiment run alongside components
that already work; nothing is rewritten for its own sake, and new work stays
Python. See §3. **Nothing has started** — it is owner-gated.

Track A does not pause for Track B. If they ever conflict, **Track A wins** —
shipping a working product beats architectural progress.

## 2. Track A — V1 capability

**Shipped since v0.2.0** (gap-analysis verdicts reconciled 2026-07-28):

- **CB6 — multi-agent consistency → PASS.** The only Critical benchmark that
  passes. `reports/INTEGRATION_CONTRACT.md` exists; the SSE contract-drift
  benchmark is green and enforcing.
- **CB5 — security validation**: the earn-the-seal filter verdict now flows
  end-to-end to the UI. Stays PARTIAL — `detect` residual (one adversarial
  payload).
- **CB4 — institutional decision memory**: durable mirror + `GET /runs/:id/decisions`,
  covering every terminal outcome including cancelled/crashed. Stays PARTIAL —
  tradeoffs are flat prose, crash-path participants incomplete.
- **CB2 — large repo understanding**: symbol tier, AST search, dep-graph
  traversal, archive ingestion, cross-call workspace persistence. Stays
  PARTIAL — architectural explanation is NOT-YET.

Outreach gate = all 6 Critical PASS + ≥1 Exceptional. Today: **1 PASS, 5
PARTIAL.**

**Open, in rough priority order:**

1. **CB3 / EB3 — real media ingestion.** Mechanism proven, actual multi-modal
   ingestion absent. Owner: memory (extractor) + orchestration (experts).
2. **CB1 / EB1 — temporal truth.** `fact|assumption` + `valid_at` typing has
   **landed**; the harness marks that discriminator PASS. What remains: retrieval
   explanation (the "why this memory"), complete provenance (author/RFC linkage),
   and explicit supersession linkage so current-vs-historical is a relationship,
   not prose. Owner: memory.
3. **Batch architecture beyond the engineering tier.** Parked pending design —
   **needs owner greenlight before anyone starts.**
4. **Budget enforcement go-live.** Code is built but ships `enforcement_enabled=False`
   and `pricing.yaml` holds **placeholder prices**. **Needs the owner to set real
   per-model prices** — the loader is fail-closed, so an un-priced model blocks
   rather than leaks. Owner: backend.

**Known limitations carried into v0.3.0** (documented, not hidden): concurrent
`code.engineer` calls in one mission race on the shared workspace snapshot;
CB4 records on the crash path have empty participants; one dev-only Dependabot
residual.

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

**Status: not started.** Blocked on a design discussion the owner asked for —
FFI vs. separate service, how a port is served across the boundary, dev loop and
deploy with two toolchains, and making that component's tests language-independent.
**Nobody starts Rust code until that discussion happens.**

## 4. Lanes by role

| Role | Current lane |
|---|---|
| **backend** (coordinator) | Track B design discussion; foundation/config seams; review + integrate + push; dispatch workers |
| **memory** | CB3/EB3 media ingestion; CB1/EB1 retrieval explanation + provenance + supersession linkage (`valid_at` typing is DONE) |
| **orchestration** | media experts for CB3; batch tier is **parked** pending owner greenlight |
| **security** | CB5 detect residual; standing invariant review of budget/batch designs |
| **api** | remaining run-lifecycle proof areas (cross-user non-disclosure sweep) |
| **frontend** | its own backlog; `HANDOFF.md` in `frontend/` |
| **release** | post-v0.3.0 housekeeping; next release when there is scope |

## 5. Needs the owner, not us

Do not start these; they are decisions, not tasks:

1. **Rust design discussion** — gates all of Track B.
2. **Batch architecture greenlight** — gates the batch tier.
3. **Real per-model prices** in `config/backend/pricing.yaml` — gates budget go-live.
4. **Whether V1 ships to real users before more capability work.** Nobody has
   used this yet, and that is the largest unknown in the whole plan.

## 6. Stale things worth fixing

- `reports/INTEGRATION_CONTRACT.md` says exception/cancellation bypasses audit
  derivation. `api/run_driver.py` now mirrors from `finally`, so the doc
  understates what ships. Owner: api.

Fixed 2026-07-28: `V1_GAP_ANALYSIS.md` verdicts + priority stars, and the
`mission/` phase statuses, are reconciled against what actually shipped. Keep
them that way in the same commit as the work (`CLAUDE.md` § keep status
current).
