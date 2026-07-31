# Dependency Version Strategy

**Status:** canonical. Owner-driven (2026-07-31).
**Scope:** every third-party dependency. Written around `pydantic-ai`, because it is
the one that hurts, but the rules are general.

---

## 1. The position

**We do not rebuild our dependencies, and we do not fear upgrading them.**

The owner's framing, and it is right: `pydantic-ai` is maintained by the team behind
`pydantic`, which trillion-dollar companies depend on. We will not out-engineer them,
and trying would be a waste of the only thing we actually have less of than they do —
time. When they ship a capability, the default is to **take it**.

Two facts make staying current urgent rather than optional:

- **They move fast.** `2.4.0` (2026-07-02) to `2.18.0` (2026-07-24) is **14 minor
  versions in three weeks**. A pin does not hold a position; it accumulates a debt
  that grows every week.
- **We are early.** Experiments are cheap now and expensive later. The cheapest time
  to make upgrades routine is before there are users.

So the goal is not "upgrade carefully sometimes". It is: **a version bump should be a
non-event, and when it is not, the failure should be loud, immediate, and specific.**

## 2. The thing that actually bites

A dependency upgrade rarely breaks us with a type error. Those are trivial — the
import fails, the suite goes red, you fix it in a minute.

What bites is a **silent behavioural change**: the API is identical, the types match,
the code runs, and a guarantee we were relying on quietly stops holding.

This happened. `pydantic-ai 2.18.0` was tried on 2026-07-27 and reverted because it
**silently broke the bounded-loop money guard** (`requirements.txt`). Nothing threw.
The bound just stopped bounding.

That is LAW 6, stated exactly:

> if an invariant (spend ceiling, loop cap, fail-closed gate) is enforced only by the
> dependency, we outsourced a promise, not isolated a dependency.

**This is not a criticism of the library.** The pydantic team cannot own our spend
ceiling — not because they are less capable, but because *they do not know our money
is on the line*. That knowledge lives here, so the guarantee has to be asserted here.

## 3. The strategy

### 3.1 One door per dependency (already true — keep it true)

`core/llm/framework.py` is the **only** module in the repo that imports `pydantic_ai`.
Every other module passes neutral types (an output schema, a prompt name, `(bytes,
mime)` media tuples, `{role, content}` history dicts) and receives validated structured
output, never an SDK object.

This is what makes an upgrade a *local* event. Protect it: a second importer turns
every future bump into a repo-wide audit. `/invariant-check` catches this.

### 3.2 Contract tests on BEHAVIOUR, not API surface

This is the load-bearing rule, and the one that was missing.

For every guarantee we depend on the library for, there must be a test that goes red
when the **behaviour** changes — not one that checks the parameter was passed.

> A test that asserts `max_turns=8` was handed to the SDK proves we configured it.
> Only a test that drives a pathological infinite loop and asserts it *stops* proves
> the bound holds.

The distinction is the same one that produced the CB5 over-claim and the prompt-cache
mistake: **a check that something is CONFIGURED is not a check that it WORKS.**

The worked example already in the tree is
`tests/orchestrator_turn_budget.py::test_orchestrator_loop_is_bounded_at_cap` — a spy
model that always requests another tool call, driven through the real agent machinery,
which fails on a too-high cap and *times out cleanly* if the cap is disabled entirely.
Copy that shape.

**The invariants that need this coverage:**

| Invariant | Why it matters |
|---|---|
| Loop/turn cap actually stops the loop | runaway agent spends real money |
| Spend ceiling refuses past the budget | same, at the wallet |
| Usage counters are real provider numbers | metering and pricing are built on them |
| Failure past a limit is fail-CLOSED | a limit that degrades open is not a limit |
| Prompt-cache settings reach the provider | cost, and the owner's token question |
| Structured output rejects a bad shape | garbage never reaches a user |

### 3.3 Bump on a branch, gated on the suite

The procedure, deliberately boring:

1. Branch. `uv pip freeze` the current set **first** — a snapshot restores exactly,
   where a downgrade of one package leaves its transitive upgrades behind.
2. Install the target version.
3. Run the **full** suite, with a live Qdrant. Without one, 12 memory/isolation tests
   skip — and they are usually the ones that matter.
4. Green → land it. Red → the failure names the invariant we outsourced. Fix *that*,
   not the version number.

A red suite on an upgrade is not a reason to re-pin. It is the strategy working: it
found an outsourced promise, which we now own.

### 3.4 A pin must carry a reason and an expiry

A pin with no reason becomes permanent, because nobody dares remove what they cannot
explain. Every pin states, in the requirements file, next to the pin:

- **what broke**, specifically (not "compatibility issues");
- **what must be proven** to unpin;
- **a re-check date**.

The existing `pydantic-ai` pin comment does the first two well. Add the third.

### 3.5 Take what they ship

Staying current is not defensive; it is how we get work for free. Capabilities in
`2.18.0` we currently do without, and would otherwise have to build:

- `cache_hit_ratio` — answers "is prompt caching actually hitting?", which we had to
  build counters for by hand.
- Deferred-tool streaming events — real lifecycle events for the UI.
- `ToolFailed` — a tool reports a model-visible failure *without* burning a retry.
- Automatic message-history repair into provider-valid tool-call/result pairings.
- Per-run retry budget overrides.

**Not applicable to us, checked rather than assumed:** the AG-UI message-history
vulnerability fixed in 2.5.0 does not reach us — `rg 'ag_ui|AGUI'` over the backend
returns nothing. Neither does the durability rewrite: no DBOS, Prefect, or Temporal
wrappers exist here.

## 4. What this is not

It is not a licence to upgrade blind. The gate is the suite, and the suite is only as
good as §3.2. **Adding a dependency version bump without the behavioural test for the
invariant it touches is how the silent break happened in the first place.**

If an upgrade is green only because no test covers the guarantee, we have not proven
anything. We have just stopped looking.
