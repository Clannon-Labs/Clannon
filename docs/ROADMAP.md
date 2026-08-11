# ROADMAP — what we're building, and who's on what

**Read this first when you need to know "what should I work on?"** It is the
single entry point; the detailed plans it points at stay authoritative for their
own areas.

Last reconciled: **2026-08-11**.

**pydantic-ai is pinned at 2.22.0** (upgraded 2026-08-01; installed version
verified 2026-08-02). The July pin at 2.4.0 blamed a broken bounded-loop money
guard; the real cause was our classifier inferring a permanent failure from the
dependency's error *text*, which 2.18 changed by adding a docs link. Fixed by
matching on the exception type, so the pin is now for reproducibility, not fear.
Upgrade procedure and what must stay true:
`docs/architecture/DEPENDENCY_VERSION_STRATEGY.md`. Re-check by 2026-08-31.

> **Standing rule:** if you finish your lane and nothing here is assigned to you,
> **that is a valid state.** Write your handoff and stop. Do not invent work
> (`docs/architecture/CREW_WORKFLOW.md` §2.2).

---

## 0. Where the detail lives

| Source | Covers | Trust it? |
|---|---|---|
| **this file** | cross-role priorities, the Rust track, who owns what | current |
| **`specification/`** | the API contract the frontend builds against, and the Rust build guide | current — routes re-verified 2026-08-09 |
| **`specification/api/requests/`** | the frontend's filed asks — **coordinator sweeps this** | current — all 5 answered 2026-08-09 |
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

**Track B — the Rust rewrite, and it is the OWNER'S, by hand.** Written from a second
machine profile — treat that as a different person who only writes Rust; the owner is
still present here and reads `proposals/`/`reports/`/`comms/` as always. They created
`backend-rust/` on 2026-08-09 and asked that nothing else touch it; `crew.sh` refuses to
dispatch a worker there and root `CLAUDE.md` carries the prohibition. **Agents write no
Rust.** Design docs live in `specification/rust/`. Owner: *"Python backend can be kept
developing to quickly build the prototype and validate the idea."*

Track A does not pause for Track B. If they ever conflict, **Track A wins** —
shipping a working product beats architectural progress. That ordering matters
more now, not less: the Python backend stays the live product for the whole
migration, and a half-built Rust core is not a reason to stop fixing it.

## 2. Track A — V1 capability

**Shipped since v0.2.0** (gap-analysis verdicts reconciled 2026-07-28):

- **CB6 — multi-agent consistency → PASS.** The only Critical benchmark that
  passes. `specification/api/SEMANTICS.md` exists (was
  `reports/INTEGRATION_CONTRACT.md`); the SSE contract-drift
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
   directories landed 2026-07-31. First slices landed 2026-08-02: memory read/write,
   central orchestrator, and engineering batch prompts now describe exact authority,
   tools, failure modes, completion rules, and model-visible surfaces; dynamic
   contracts fail when runtime capability and prompt drift. Remaining: expert
   prompts, other batches as they exist, and real A/B quality/latency evidence.
   Owner: backend + memory + orchestration.
5. **Memory read-side LLM (owner-ratified 2026-07-31).** Keep vector search; add a
   lightweight LLM that retrieves exactly what the orchestrator needs. It must
   reach memory ONLY through powerful, precise tools — it must not be able to open
   and read memory directly. That constraint is also what keeps tenant isolation
   enforceable. First conditional slice landed 2026-08-02 behind Manager after
   verifier success: tenant/tier scope stays outside model schema, returned candidates
   use opaque run-local ids, and deterministic hydration remains default. Real
   synthetic Haiku proof completed in 9.45s inside a separate 15s bound; real
   user-memory relevance/quality remains unproven. Owner: memory.
6. **Guard false positives (owner-ratified 2026-07-31, option 1 only).** Cut false
   positives by making the guards MORE DISCRIMINATING — better examples, sharper
   instructions per the guide. **NOT by lowering the bar**: owner chose this
   explicitly over compromising detection. `verifier`/`filter` are `locked: true`
   and CB5 is PARTIAL *because detection already evades on paraphrase*, so any
   change runs against `tests/benchmarks/cb5_verdict_honesty.py`. Identity handling
   now distinguishes denial, quotation, comparison, and questions from direct or
   indirect provider attribution, with over-block and under-block mutations. Broader
   CB5 remains PARTIAL. Owner: security.
7. **Budget enforcement go-live.** Fixed anniversary periods, confirmed mock
   add-on/upgrade settlement, and coarse server-side run admission landed
   2026-08-01. Admission honestly checks completed current-period usage before
   creating a root/follow-up/revision; one admitted run can still overshoot and
   concurrent admissions can race. Exact per-call Redis money-cost enforcement
   is built but ships `enforcement_enabled=False`. Owner supplied provider-pricing references;
   backend must verify them against official current prices, represent
   tier/modality differences honestly, measure conservative infrastructure
   cost, seed production budgets, prove recovery/concurrency, and obtain
   security review. Atomic reserve/reconcile, concurrency, seeding primitives, and the
   LLM anchor are built; reconciliation now stays pinned to the period that granted its
   hold even across a billing boundary. Still open: broker/seeding must use the API's
   fixed anniversary period instead of the broker's calendar-month default, plus durable
   recovery/true-up for failed reconciliation. Loader stays fail-closed. Create a fresh
   owner go-live proposal only when those engineering gates are green. Owner: backend.

**Known limitations carried into v0.3.0** (documented, not hidden): one dev-only
Dependabot residual.

## 3. Track B — Rust

**The rule, in two halves. Both matter:**

### 3a. New backend behaviour → still Python, until its port is ported

**New work still lands in Python first.** Not because Python is preferred, but
because §3b's method requires it: a Rust implementation is validated by diffing it
against a working Python one, so writing new behaviour directly in Rust is a
different strategy — greenfield, no safety net — smuggled in under the same heading.

The exception is the Rust core itself, which is a *port* of behaviour that already
exists, not new behaviour. When a subsystem has completed cutover (§3b step 5), new
behaviour for that subsystem is written in Rust, because by then Rust is where it
lives.

**Stays TypeScript:** the whole frontend. Not up for discussion, and the ruling makes
this more important — the frontend's contract should not notice the migration at all
(`rust/DECISIONS.md` §10).

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

**Status: NO LONGER DEFERRED — owner ruling 2026-08-02.** The backend splits into
a Rust core (`clannon-core`: pipeline, memory, tools, experts, orchestration,
security, registry, budgets, **and the API the frontend talks to**) and a Python
worker (`clannon-ai-runtime`: model calls only). Two services, HTTP/JSON, no FFI.

The owner's decisive argument was maintainability, not performance: an agent wrote
most of these 30,467 lines, agent hours are finite, and hand-writing the core is how
the owner comes to own the system. Migration cost is also superlinear in codebase
size, and post-V1 the stability promise makes a rewrite impossible — so "wait for V1"
does not make this cheaper, it makes it never happen.

Design lives in **`specification/rust/`** (moved there 2026-08-02 from
`docs/architecture/rust/` — a build contract is not documentation of what exists).
All `[PROPOSED]`, awaiting ratification. Start at `specification/rust/README.md`;
`DECISIONS.md` holds the boundary rule and every piece of rationale,
`CONFORMANCE_HARNESS.md` holds how either language is proven correct.

**Division of labour:** the owner writes the Rust. Agents build the conformance
harness — the 33,420 lines of existing tests import Python modules directly and
cannot validate Rust, so the core would otherwise start with zero validation. Agent
hours go to the harness, not to more Python the owner has to understand.

Pilot is still the Redis budget broker (485 lines, off in production). Its definition
of done is deliberately *not* "the Rust works" — it is "the harness is proven to catch
a wrong implementation."

**Validation split, settled 2026-08-02.** The owner writes Rust *and* wants agents
writing Rust-native tests from it, with the Python tests as reference. That stands,
with one correction: **mirrored per-language tests cannot detect drift** — an agent
writing a Rust test reads the Rust, so a self-consistent Rust bug produces a green
test. Drift detection requires **one shared scenario file run against both languages**.
Rust-native tests keep their own job (panics, ownership, concurrency); they are simply
not the drift detector.

The 2026-07-28 boundary ruling (separate process + versioned API, FFI only for bounded
pure computation) still stands and this follows it.

## 4. Lanes by role

| Role | Current lane |
|---|---|
| **backend** (coordinator) | existing-system hardening; Redis-budget design/review; foundation/config seams; review + integrate + push; dispatch workers |
| **memory** | CB3/EB3 media ingestion; CB1/EB1 retrieval explanation + author/RFC provenance + supersession linkage (Manager-only curation/save provenance DONE) |
| **orchestration** | central/batch prompt contracts landed; continue Mission Engine + batch hardening, propose-first where owner-gated |
| **security** | standing invariant review of budget/batch designs; widen adversarial regression coverage when new classes appear |
| **backend-audit** | establish backend/root threat model; baseline adversarial audit; targeted deep review of money, identity/tenant, network/tool, sandbox, and fail-closed boundaries; report only |
| **frontend-audit** | establish browser/client threat model from frontend charter; baseline adversarial audit; deep review of rendered content, iframe/URL handling, identity/storage, SSR/client divergence, third-party surface, and backend-enforced controls; report only |
| **api** | remaining run-lifecycle proof areas (cross-user non-disclosure sweep) |
| **frontend** | its own backlog; `HANDOFF.md` in `frontend/` |
| **release** | post-v0.3.0 housekeeping; next release when there is scope |

## 5. Needs the owner, not us

**One open gate.**

**Security campaign status (2026-08-11): STOP.** Independent backend retest at
`e34f1f42` marks launch-control F-01 through F-04 mitigated in bounded local scope:
canonical production mode/YARA, mail startup preflight, private-alpha outbound
mutation denial, and ASGI waitlist response ordering. This is not whole-system PASS.
Frontend remediation still awaits independent retest; its full Playwright suite is
blocked by stale mock tests that still use removed public signup. Server citation
projection also still emits arbitrary URL schemes. Missing production YARA rules fail
the first scan, not application readiness. Deferred identity/tenancy, SSRF, uploads,
execution, persistence, availability, secrets, supply-chain, and real deployment
surfaces remain open; do not invite testers until evidence changes this gate. Reports:
`reports/backend-audit/report_v2.md`, `reports/frontend-audit/report_v1.md`.

**RULED 2026-08-09 — signup gating.** Owner chose a **waitlist**, not the allowlist
recommended: email + optional note → verify inbox → owner approves individually.
Built and shipped (`97dfdb7`). Remaining is owner-side infrastructure, not a decision:
a Resend account, `RESEND_API_KEY`, and `CLANNON_MAIL_FROM` on a domain with SPF/DKIM.
`LogMailer` refuses to start in production until then. Superseded text below kept only
for the finding that produced it:

<details><summary>original gate (resolved)</summary>

**Signup is not gated, and we call this a private alpha** —
`proposals/to-owner/2026-08-09_signup-is-not-gated-for-private-alpha.md`. `POST
/auth/signup` has no invite code, allowlist, or approval step (`api/app.py:193`,
`api/auth.py:177`); anyone reaching the URL gets a full account. Found by the frontend,
verified by backend. Owner picks one of three shapes; recommendation is the email
allowlist. **Blocks going live on the domain**, nothing else. Enforcement and tests are
engineering's once the shape is chosen.

</details>

**Still open:** confirm the boundary rule's second clause —
`proposals/to-owner/2026-08-02_boundary-rule-second-clause.md`. Presidio has no Rust
equivalent, so the one-clause rule says "port it" and that is impossible. Carried in
`rust/DECISIONS.md` as D3a marked *pending owner confirmation*, so nothing is silently
assumed. Does not block Phase 0.

Closed 2026-08-02: contract ratification (all three ruled) and document structure
(approved; the five-doc set is written).

Ruled 2026-08-02 (contract ratification, now archived): frontend contract does **not**
change but the existing 33-route API must be specified before the owner can build
against it; **contract-first**, with the contract in points and tables rather than
prose and a dedicated protocol document; **Python owns provider keys**.

Settled by the 2026-07-28 rulings, still standing:

- shared 50 MiB upload/archive cap plus bomb guards ratified;
- Python capability work continues while owner recruits a small real-user
  cohort in parallel;
- separate-process/FFI boundary settled — the 2026-08-02 Rust ruling follows it;
- official model-price verification and infrastructure measurement assigned to
  engineering. Final budget-enforcement go-live remains owner authority, but no
  proposal is created until engineering gates are green.

This section and `proposals/to-owner/` must agree. New owner proposal means
owner can act now; future gates stay in their engineering plan until ready.

## 6. Stale things worth fixing

Nothing currently known-stale.

Fixed 2026-08-02: this file's header still said pydantic-ai was "UNPINNED at
2.18.0" while `requirements.txt` pinned 2.22.0 and the venv had 2.22.0 installed.
A version claim is exactly the kind of line an agent trusts without checking, so
it now names the pin and records that the installed version was verified, not
assumed.

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
