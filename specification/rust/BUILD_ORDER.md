# BUILD ORDER

What to build, in order. Open this when you sit down and want to know the next thing.

**Rule:** every item has a `done` you can check without asking anyone. If you cannot
tell whether an item is finished, the item is written wrong — say so.

**Who does what:** you write Rust. Agents write the conformance harness, the Python
runtime, and the port refactors. Nobody writes Rust but you.

---

## Phase 0 — the boundary, in Python only

**No Rust in this phase.** The point is to prove the boundary before it is *also* a
language boundary. If the contract is wrong you find out in Python, in a day.

| # | Item | Who | Done when |
|---|---|---|---|
| 0.1 | `services/ai-runtime/` — the Python runtime serving `/v1/*` per `PROTOCOL.md` | agents | all four endpoints respond; `/v1/capabilities` returns `1.0` |
| 0.2 | `core/llm/` becomes a **client** of it | agents | the pipeline runs end-to-end with the runtime as a separate process; full suite green |
| 0.3 | Kill-the-runtime test | agents | runtime down → every layer degrades honestly, no run crashes |
| 0.4 | `dev/` scripts | agents | `dev/dev.sh` brings up runtime + backend + frontend |

**Phase 0 done = the product works, unchanged, with the model calls on the far side of
an HTTP boundary.** That is the whole gate. If it does not hold, do not start Phase 1.

---

## Phase 1 — the harness, on one subsystem

Target: **`core/budget/`** — 485 lines, `enforcement_enabled=False`, zero ML, already
has a process boundary via Redis.

| # | Item | Who | Done when |
|---|---|---|---|
| 1.1 | `BudgetPort` is the only door to `core/budget/` | agents | nothing outside imports its internals |
| 1.2 | `conformance/scenarios/budget/*.yaml` | agents | every port method + every failure path covered |
| 1.3 | `adapters/python_inproc.py` | agents | all scenarios green against today's Python |
| 1.4 | Mutation gate | agents | every **semantic** mutation turns the suite red |
| 1.5 | Runs in < 60s locally | agents | timed |

> **Phase 1's definition of done is NOT "the Rust works" — no Rust exists yet.** It is
> *"the harness is proven to catch a wrong implementation."* Reaching that with zero
> Rust written is a success: it means you can start writing Rust against a target that
> tells the truth.

A mutation that stays green is a hole in the harness. Fix the harness, not the
mutation, before moving on.

---

## Phase 2 — first Rust

| # | Item | Who | Done when |
|---|---|---|---|
| 2.1 | `services/core/` cargo workspace | **you** | `cargo build` succeeds |
| 2.2 | Rust budget broker behind the same port shape | **you** | compiles, runs |
| 2.3 | `adapters/rust_http.py` | agents | same scenarios run against Rust |
| 2.4 | Scenario parity | **you** + agents | identical scenario set green on both |
| 2.5 | Differential run, incl. concurrent interleaved reserves | agents | no observable divergence |
| 2.6 | Rust-native tests (panics, ownership, concurrency) | agents | green |

**Do not cut over yet.** Phase 2 ends with two implementations that agree.

---

## Phase 3 — repeat, in this order

Ordered by how boundary-clean each is today. Same six steps as Phase 1+2 per subsystem.

| Order | Subsystem | Lines | Why here |
|---|---|---|---|
| 1 | `core/budget/` | 485 | pilot, done above |
| 2 | `core/intake/` + `core/normalizer/` | 619 | small, pure, few dependents |
| 3 | `security/` | 2,165 | fail-closed and well-tested; high value, clean seam |
| 4 | `registry/` | 3,807 | prompts + model routing; mostly config resolution |
| 5 | `core/verifier/` | 788 | one LLM call, clean in/out |
| 6 | `tools/` + `experts/` | 2,547 | needs the runtime client working |
| 7 | `core/orchestrator/` | 1,700 | the loop; needs 6 first |
| 8 | `core/memory/` | 4,589 | biggest; embeddings come with it |
| 9 | `api/` | 4,545 | last — needs everything under it |
| 10 | `foundation/` | 3,161 | **truly last**; 209 in-process importers, so porting it early means FFI on the hottest path for the whole migration |

`delivery/` (44 lines) rides with whatever needs it.

---

## Phase 4 — cutover, per subsystem

| # | Item | Done when |
|---|---|---|
| 4.1 | Route the port to Rust | scenarios green through the Rust path in production config |
| 4.2 | Python stays as fallback | a flag flips back without a deploy |
| 4.3 | Time-box the fallback | a date is written down |
| 4.4 | Delete the Python | after the date, with git history as the real fallback |

Permanent parallel dead paths violate LAW 1. The fallback is temporary by design.

---

## Standing rules

| Rule | Why |
|---|---|
| Track A wins | The Python backend is the live product for the entire migration. A half-built Rust core is never a reason to stop fixing it. |
| New behaviour lands in Python first | Until a subsystem cuts over. Rust validates by diffing against a working Python. |
| A scenario is the contract | If Rust fails a scenario, check the Python's real behaviour before "fixing" the Rust. A suite that ossifies a Python bug into a cross-language requirement is worse than none. |
| Frontend contract does not change | `sse_contract_drift.py` keeps CB6 green through the migration. |
