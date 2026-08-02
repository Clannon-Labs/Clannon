# The conformance harness — proving Rust and Python behave identically

**Status:** `[PROPOSED]` — design only, nothing built. Companion to
`CORE_RUNTIME_CONTRACT.md`. This is gate #2 of the four in
`RUST_MIGRATION_STRATEGY.md` §"Before any port starts": *language-independent
conformance tests through the port/API.*

---

## 1. The problem, measured

The backend has **33,420 lines of tests** against **30,467 lines of non-test Python**.
That is an unusually good ratio and it is the main reason the system is trustworthy.

**None of it can validate Rust.** Every test imports Python modules directly:

```python
from core.memory import store          # a Rust store cannot satisfy this
manager = MemoryManager()              # nor this
```

So a Rust core inherits **zero** validation. Hand-writing ~29,000 lines of Rust at a
couple of hours a day, with no signal telling you when it disagrees with the Python
that works today, is the way this fails — not from lack of skill, from lack of a
red/green light.

**The harness is that light.** It is the highest-value thing agent hours can buy on
this migration, and it is the natural division of labour: the owner writes the Rust,
because writing it is how you come to own the system; the agents build the thing that
proves the Rust is right, because that is mechanical, high-volume, and adds nothing to
the pile of code the owner would otherwise have to understand.

---

## 2. The one rule that makes a test language-independent

> **Assert only on what crosses the port. Never on how it got there.**

A conformance test may assert on returned values, returned errors, and observable
state read back **through the same port**. It may never assert on a Redis key shape,
a Qdrant payload field, a Python attribute, a log line, or a call count.

This is stricter than the current suite, and deliberately so. The current suite's
freedom to reach inside is exactly why it cannot be reused.

---

## 3. Three layers

### Layer 1 — Scenario conformance (the workhorse)

Scenarios are **data, not code**, so one file runs against both languages. A driver
executes them against a selected target adapter.

```yaml
name: reconcile_releases_the_unspent_reservation
port: budget
steps:
  - call: reserve
    with:   {scope: run, key: run_1, amount_usd: "0.50"}
    expect: {ok: true, reservation_id: $res}
  - call: reconcile
    with:   {reservation_id: $res, actual_usd: "0.20"}
    expect: {ok: true, released_usd: "0.30"}
  - call: balance
    with:   {scope: run, key: run_1}
    expect: {spent_usd: "0.20"}
```

Two target adapters, same scenarios, selected by `CLANNON_CONFORMANCE_TARGET`:

- `python-inproc` — imports today's implementation. Fast; this is the **oracle**.
- `rust-http` — speaks the §5 contract to the running Rust service.

**Failure paths are first-class.** A scenario that asserts a broker-down reserve
*fails closed* is worth more than ten happy-path scenarios, because fail-closed is the
behaviour a reimplementation is most likely to get subtly wrong.

### Layer 2 — Differential testing (finds what nobody imagined)

Drive both implementations with the same generated call sequence and diff the
observable results. Randomised and concurrent sequences go here — for the budget
broker specifically, interleaved concurrent reserves against a shared ceiling, which
is precisely where a lost-update overspend would hide and precisely what a
hand-written scenario tends to miss.

Later this can replay recorded production call sequences. Not for v0.

### Layer 3 — Invariant scenarios (the things that must never break)

The same format, but encoding guarantees rather than features. These are copied from
`INVARIANT_OWNERSHIP.md` and must hold in **any** language:

- a reserve/reconcile cycle never lets total spend exceed the ceiling, under
  concurrency;
- a down broker fails closed, never open;
- `user_id` scoping: no user id ⇒ no memory, and never another tenant's row;
- the output filter is the only thing that clears a report to the user;
- the loop cap holds regardless of what a provider's error text says.

---

## 4. The mutation gate — without this the harness is decoration

A green harness proves nothing until it has been shown to go **red** when the
implementation is wrong.

This repository has already paid for that lesson once. On 2026-07-28 CB5 was marked
PASS because new rules turned its benchmark green; the rules had been fitted to the
benchmark's exact wording. Deleting a rule *did* turn the suite red — so the ordinary
mutation check passed — and the verdict was still wrong, because **non-vacuous is not
the same as generalising.**

So the gate has two tiers, and the second is the one that matters:

1. **Structural mutations** — delete a branch, skip a call. Harness must go red.
2. **Semantic mutations** — change behaviour in a way the requirement says must still
   be caught, while keeping the code plausible. *Reconcile releases the full
   reservation instead of the unspent remainder. Fail-closed becomes fail-open only
   when the broker times out rather than refuses. Tenant filter applied on read but
   not on delete.* Each of these **must** turn the harness red.

A mutation that stays green is a **hole in the harness**, and it is fixed before any
Rust is written against that port. Mutations live beside the scenarios and run in CI,
because a harness silently rots the same way a test does.

---

## 5. Sequencing per subsystem — the step everyone skips

**You cannot write a cross-language conformance test for a subsystem that has no
seam.** Most of the ~29,000 lines have no port today. So the order is:

| Step | Who | What |
|---|---|---|
| 0 | agents | Ensure a `foundation/contracts/` port exists and the Python implementation is reached **only** through it |
| 1 | agents | Write scenarios + adapter; prove green against `python-inproc` |
| 2 | agents | Mutation-gate the harness (§4) until every semantic mutation goes red |
| 3 | **owner** | Write the Rust implementation against the scenarios |
| 4 | agents | Differential run; fix scenarios that were ambiguous, not the Rust |
| 5 | both | Cut over at the port boundary; Python stays a time-boxed fallback, then is deleted |

**Step 0 is why this bet is safe even if the Rust stalls.** Forcing every subsystem
behind a real port is LAW 6 work that improves the Python codebase on its own terms —
one door per dependency, swappable by design. If the migration paused for a year, that
work would still have been worth doing. Very little else about this migration has that
property, and it is the reason to start here rather than anywhere else.

---

## 6. Pilot: the budget broker

`core/budget/` — 485 lines, `enforcement_enabled=False` so nothing live is at risk,
zero ML, already has a process boundary via Redis, and already ratified as the pilot.

It is also the *right* pilot for a reason beyond size: money is where "behaves
identically" has to mean something exact, and the atomic reserve/reconcile is a real
concurrency contract rather than a CRUD surface. If the harness cannot express
"never overspends under interleaved concurrent reserves," it is not going to survive
memory or orchestration, and we want to learn that on 485 lines.

**Definition of done for the pilot — and it is deliberately not "the Rust works":**

- scenarios cover the BudgetPort surface including every failure path;
- every semantic mutation of the Python turns them red;
- the identical scenario set runs green against `python-inproc`;
- the harness runs in under a minute locally, because a slow signal is an unused one.

Reaching that with **no Rust written at all** is a success. It means the mechanism is
proven and the owner can start writing Rust against a target that tells the truth.

---

## 7. Where it lives

```
conformance/
  scenarios/
    budget/*.yaml
    memory/*.yaml
  adapters/
    python_inproc.py
    rust_http.py
  mutations/
    budget/*.patch
  driver.py
```

Top-level, **not** under `backend/tests/`. It is not a backend test — it is a
cross-language contract suite that outlives the Python. Keeping it at the root is what
stops it being quietly rewritten to import Python internals the first time that is
convenient.

---

## 8. Honest risks

**The harness can be wrong.** It encodes what we *believe* the Python does. Where
belief and behaviour differ, the scenario is wrong and will be discovered by the Rust
failing a test it should pass. When that happens: **check the Python's actual
behaviour before "fixing" the Rust.** A conformance suite that ossifies a Python bug
into a cross-language requirement is worse than none.

**Scenario coverage is not behaviour coverage.** Layer 1 only tests what someone
thought to write down. Layer 2 exists precisely because that is never enough, and it
should not be treated as optional polish.

**This is real work, and pretending otherwise would be dishonest.** The budget pilot
is small; memory and orchestration are not. The estimate to carry to the owner is per
subsystem, at step 0 and step 1, once the pilot has given us a real data point —
**not** a number invented now.
