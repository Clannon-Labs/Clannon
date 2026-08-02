# Rust core — document index

The backend splits into **`clannon-core`** (Rust) and **`clannon-ai-runtime`** (Python).
Owner ruling 2026-08-02. Everything here is `[PROPOSED]`; nothing is built.

**Which file do I open?**

| Doc | What's in it | Format | Open it when |
|---|---|---|---|
| [`PROTOCOL.md`](PROTOCOL.md) | The Rust↔Python wire. Endpoints, every field, every enum, every error class. | tables only | writing the Rust client or the Python server |
| [`../api/ROUTES.md`](../api/ROUTES.md) | All 38 existing frontend-facing routes — purpose, auth, gotchas. | tables + detail | building the Rust API surface |
| [`BUILD_ORDER.md`](BUILD_ORDER.md) | What to build, in order, with a checkable `done` per item. | phased tables | sitting down and asking "what now" |
| [`CONFORMANCE_HARNESS.md`](CONFORMANCE_HARNESS.md) | How either language is proven correct. The mutation gate. | design | building or trusting the test harness |
| [`DECISIONS.md`](DECISIONS.md) | Why the boundary is where it is. All the rationale, D1–D9. | prose | something looks wrong and you want to know why |
| [`IDIOMS_AND_CRATES.md`](IDIOMS_AND_CRATES.md) | Which Rust features and crates to use where, and what they replace. | tables | choosing how to build a piece |

**The rule everything follows:** *does it need a network call to a model provider, or a
Python-only ML ecosystem? → Python. Everything else → Rust.*

The second clause was added 2026-08-02 (`DECISIONS.md` D3a, pending owner confirmation)
because Presidio has no Rust equivalent — the one-clause rule said "port it" and that is
impossible.

**Division of labour:** the owner writes the Rust. Agents write the conformance
harness, the Python runtime, and the port refactors.

**Start at** `BUILD_ORDER.md` Phase 0 — which contains no Rust, deliberately.

Related: [`../../docs/architecture/RUST_MIGRATION_STRATEGY.md`](../../docs/architecture/RUST_MIGRATION_STRATEGY.md)
(canonical for *how* a port happens), [`../../docs/ROADMAP.md`](../../docs/ROADMAP.md) §3,
[`../api/`](../api/) (the surface Rust must serve unchanged).
