# Rust migration strategy — how we port, and what we refuse to do

**Status: CANONICAL for HOW a port happens.** Owner-set 2026-07-27; process
boundary settled 2026-07-28. Related: `LAW/README.md` LAW 6 (replaceability) —
this doc is *how* we exercise the property that law requires us to keep.

> **Superseded on WHEN and WHAT, by owner ruling 2026-08-02.** This document was
> written when Rust was a deferred experiment on isolated components. The owner
> has since decided to split the backend into a Rust core (`clannon-core`) and a
> Python model-calling worker (`clannon-ai-runtime`), starting now rather than
> after V1 — the argument being that migration cost is superlinear in codebase
> size, that post-V1 stability makes a rewrite impossible, and that the owner
> needs to hand-write the core to understand a system an agent largely wrote.
>
> **Everything in this doc about process still holds** — parallel implementation,
> port-boundary cutover, conformance tests before any port, no big-bang. What has
> changed is the scope and the direction of the API boundary. See
> `rust/CORE_RUNTIME_CONTRACT.md` and `rust/CONFORMANCE_HARNESS.md`.

---

## The rule — corrected 2026-07-27 (second pass)

**V1 ships in Python. Rust is an experiment run alongside code that already
works. New code stays Python for now.**

An earlier version of this doc said "new infrastructural code prefers Rust."
**That was wrong, and it contradicted the rest of this document.** Recorded here
rather than quietly deleted, because the reasoning matters:

> Parallel implementation with deferred cutover **requires an existing
> implementation to run alongside and validate against.** New code has no Python
> counterpart, no reference behaviour, and no test suite proving what "correct"
> means. Writing it in Rust is therefore a *different* strategy — greenfield, no
> safety net — smuggled in under the same heading. The doc was holding two
> incompatible strategies at once.

There is a second reason, which is about learning: porting an already-built
component means you are learning Rust against known-correct behaviour you can
diff against. Writing something new in Rust means learning the language *and*
designing unproven behaviour simultaneously, with nothing to check yourself
against. The first is how you get good at Rust in this codebase; the second is
how you get a subtly wrong service nobody notices.

### What this means concretely

1. **New work is written in Python.** Including new infrastructure. V1 is not
   done and has never faced a user; a second toolchain per new component is a
   tax we do not need to pay yet.
2. **Modularity is non-negotiable regardless** — LAW 6. Every dependency behind
   one door, every subsystem behind a `foundation/contracts/` port, so *any*
   part could be swapped for another language or framework if we chose to. The
   point is that we are always **able** to, not that we always **do**.
3. **Rust experiments target already-built, working, well-understood
   components** — written 1:1 alongside the Python, which stays live. That is
   the process below, and it is the only Rust that happens for now.
4. **Revisit "new code in Rust" after V1 ships.** It may well be right then. It
   is not right while the product is unfinished.

If a new component genuinely demands Rust-level performance or safety
guarantees that Python cannot give, that is a proposal with a specific
argument — not a default.

## The process for a Rust experiment on existing code

**Parallel implementation with deferred cutover. Never a big-bang rewrite.**

For any part we decide to experiment with:

1. **Write the Rust 1:1 alongside the Python.** A mechanical port, minimal
   behavioural change. The Python keeps running and stays the live path.
2. **Both exist simultaneously.** The Rust implementation is inert — built,
   tested, but not serving traffic — until it earns the swap.
3. **Cut over only when the Rust is proven ready**, against the same behaviour
   the Python already guarantees. Detach Python, attach Rust, at the port
   boundary.
4. **Keep the Python after cutover** as the fallback, until the Rust has held in
   production long enough to trust (see "How long is 'just in case'" below).

The seam that makes this possible already exists: `foundation/contracts/` ports
(`MemoryPort`, `GraphPort`, `BudgetPort`, `ArtifactStore`). Consumer and
implementer never import each other, so swapping an implementation is a local
change — which is exactly what LAW 6 requires us to maintain.

**Nothing gets rewritten just because it could be.** Declining a rewrite must
mean "we didn't think Rust would make it better," never "too risky to try."

## Why not big-bang — and the honest counter-example

Bun rewrote its runtime from Zig to Rust and merged it on 2026-05-11: ~1.01M
lines, 6,755 commits, 11 days, a fleet of parallel Claude agents, ~$165k in API
cost. It worked. They explicitly **rejected** incremental porting on the grounds
that a side-by-side migration would take a small team a year with bugfixes and
features frozen throughout. The Zig codebase was **not** retained — v1.3.14 was
the last Zig release.

So the highest-profile precedent did the opposite of what we're choosing. That
is worth stating plainly rather than pretending it supports us.

**What made their big-bang survivable is the part we should actually copy:**

| Bun had | We have |
|---|---|
| 60,624 tests / 1,386,826 `expect()` calls, **0 skipped or deleted** during the port | ~37k lines of pytest |
| A **language-independent** test suite — tests exercise the runtime's public behaviour, so they validate Zig and Rust equally | **pytest importing Python modules directly** — they cannot test a Rust implementation at all |
| Adversarial review: separate Claude instances reviewing without seeing implementer reasoning, told to hunt bugs | coordinator review of every worker diff (same idea, smaller scale) |
| 11 rounds of security review, 24/7 coverage-guided fuzzing | security specialist review, no fuzzing |

**The gap that decides our approach: our tests are not language-independent.**
Bun could swap the implementation because their tests never knew what language
was underneath. Ours import `core.llm`, patch `api.auth._db`, and assert on
Python objects. They validate *this implementation*, not *the behaviour*.

That is not an argument against Rust. It is the concrete prerequisite:

> **Before any component is ported, its tests must be able to validate an
> implementation in either language** — driven through the port/API, not through
> Python internals. If the tests can't do that, the port has no safety net and
> the parallel strategy above is theatre.

This is also why parallel-with-cutover is right for *us* specifically: it lets
the Rust implementation be validated against the running Python behaviour, which
partly substitutes for the language-independent suite we don't have yet.

One further note on the Bun precedent: the Zig creator publicly called the
result "unreviewed slop" (2026-07-14). Consider the source — he has an obvious
stake — and the 99.8% test compatibility argues otherwise. But the criticism
names the real risk of AI-driven porting, and it lands on the reviewer, which
here is the backend coordinator. Review depth is the control, and it does not
scale by wishing.

## How long is "just in case"

Keeping the Python fallback forever collides with LAW 1 (no dead code, no
parallel paths). Both rules are right; the resolution is that the fallback is
**time-boxed, not permanent**:

- Keep the Python path until the Rust has served production for an agreed window
  with no correctness or performance regression.
- Then **delete it.** Git history is the real "just in case" — a deleted
  implementation is one `git revert` away, and unlike live dead code it cannot
  drift, cannot be half-maintained, and cannot confuse the next reader about
  which path is real.
- While both exist, exactly one is live. Never both serving. A flag or the port
  binding decides, and it is obvious from the code which one is in use.

The window is per-component and set when the cutover is planned, not left open.

## Sequencing

Ports that are small, off, and boundary-clean go first. `foundation/` goes
**last**, not first — 209 modules import it in-process, so a language boundary
there means FFI on the hottest path in the system, held for as long as the
migration runs. It can be ported cleanly only once the things it connects are
already Rust, at which point it is a consolidation rather than a boundary.

Current agreed pilot: the Redis budget broker (`core/budget/`) — port ratified,
~485 lines, `enforcement_enabled=False` so nothing live is at risk, zero ML, and
it already has a process boundary via Redis.

## Cross-language boundary — settled 2026-07-28

Default for a stateful or long-running Rust subsystem: **separate supervised
process with a versioned schema**. Start with HTTP/JSON when inspectability and
portable tooling matter; a Unix socket may carry the same protocol when both
processes are always colocated. Adopt gRPC only when measured volume, streaming,
or generated cross-language contracts justify its operational cost.

Use FFI/PyO3 only for a bounded function-like operation: bounded input, bounded
output, no lifecycle ownership, no complicated persistent state, and profiling
showing service serialization/call overhead matters. Native code shares
Python's crash and memory boundary, so FFI is not the default for a subsystem.

~~TypeScript continues to call the Python API over HTTP/WebSocket. Rust stays
behind Python-owned application contracts unless a specific architecture
proposal proves another route necessary.~~

**Reversed by owner ruling 2026-08-02.** Rust owns the API the frontend talks to;
Python sits *behind* Rust as a model-calling worker, not in front of it. The
frontend's contract should not change — the recommendation in
`rust/CORE_RUNTIME_CONTRACT.md` §10 is that Rust serves the identical HTTP/SSE
surface, so the frontend never learns which language answered and
`sse_contract_drift.py` keeps enforcing.

Language choice follows ownership, failure boundary, testability, and measured
benefit — not “everything non-ML goes to Rust” or “everything slow goes to
Rust.” Broad category rules would recreate a rewrite mandate under another
name.

## Before any port starts

Track B is deferred while Python V1 advances. Starting a specific port requires:

1. a proposal naming concrete safety/performance/operability benefit;
2. language-independent conformance tests through the port/API;
3. versioned request/response and failure/degradation behavior;
4. dev, build, deploy, supervision, rollback, and observability story for both
   toolchains.

The boundary question is settled; these component-specific proofs are
engineering gates, not another general owner discussion.
