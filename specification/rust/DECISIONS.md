# DECISIONS — why the Rust boundary is where it is

**This is the essay.** All rationale lives here so the other documents stay pure
reference. Open this when something looks wrong and you want to know why it was chosen.

Status: `[PROPOSED]`, owner ruling 2026-08-02. Nothing built.

---

## D1 — Start now, not after V1

**Decision:** split the backend into a Rust core and a Python model worker, beginning
immediately, reversing the 2026-07-28 ruling that deferred Track B.

**Why.** Three arguments, in increasing order of strength.

1. Migration cost is superlinear in codebase size. Today the backend is 30,467 non-test
   lines, and V1 is perhaps a tenth of the way to its eventual size.
2. Post-V1, "stable" is the promise. A rewrite then breaks it, and would take months
   the owner cannot spend.
3. **The one that actually decides it:** an agent wrote most of this code, agent hours
   are finite and paid for, and the owner needs to maintain a system they understand.
   Hand-writing the core is how you come to own it. That is a maintainability argument
   and it stands without either of the others.

**The objection, and why it does not hold.** A fork chasing a codebase that agents keep
moving never catches up — the classic rewrite failure. It does not apply here because
agent work is budget-limited to a couple of hours a day, and the owner is deliberately
trading agent velocity for comprehension. The target is not moving at agent speed.

**What we accept:** ~29,000 lines get rewritten. Calling that "introducing Rust slowly"
would be false; it is a backend rewrite with a provider shim kept in Python.

---

## D2 — Rust drives the agent loop; Python is stateless

**Decision:** Python performs exactly one model call per request and holds no state
between calls. Rust holds the conversation, executes tools, counts turns, spends
budget, and decides when to stop.

**The alternative** was Python keeping pydantic-ai's multi-turn loop and calling back
into Rust for each tool. That works and reuses more of the library — but it makes
Python the orchestrator and Rust its tool server, and it needs bidirectional RPC.

**Why we did not take it.** LAW 6: *if an invariant is enforced only by the dependency,
we outsourced a promise, not isolated a dependency.*

> On 2026-08-01 our bounded-loop money guard was found broken. pydantic-ai 2.18 had
> appended a help link to `UsageLimitExceeded`'s message — `...see the docs on usage
> limits` — and `usage limits` was one of our provider rate-limit markers. A hit spend
> ceiling classified as a transient rate limit and got **retried past the ceiling it
> exists to enforce.** No API changed. A sentence moved.

That is precisely the failure mode of leaving the loop cap and the spend ceiling inside
the dependency. Rust-drives puts both on our side of the wire, where we own them.

**The cost, stated honestly:** we reimplement turn management and lose pydantic-ai's
multi-turn machinery. Single-call use still buys provider abstraction, request shaping,
structured-output validation and usage extraction — the genuinely provider-specific
part. If someone later proposes moving the loop back into Python for convenience, the
money-guard incident is the reason not to.

---

## D3 — The boundary is a rule, not a module list

**Decision:** *does it make a network call to a model provider?* No → Rust.

A list of module names invites argument every time a new component appears. The rule
answers by itself, and it produced two corrections to the original sketch:

| Component | Sketch | Rule says | Why |
|---|---|---|---|
| embeddings | Python | **Rust** | `core/memory/embeddings.py` is fastembed nomic — **local ONNX**, no network call. The ~500MB is a one-time download. Python-side would turn five in-process calls per turn into five network hops (`hydration.py:83`, `deep_reader.py:212`, `curator.py:92`, `write_policy.py:222`, `:477`). |
| reranking | Python | **n/a** | Does not exist — zero non-test matches. Do not draft contract surface for a component that is not there. |

"Touches a model" is the wrong test. "Calls a provider over the network" is the right
one.

### D3a — the rule needs a second clause (found 2026-08-02, pending owner confirmation)

Crate research (`IDIOMS_AND_CRATES.md` Part 3) found the rule as written does not
survive contact with `security/`. **Presidio has no Rust equivalent and will not get
one.** PII detection is `presidio-analyzer` over spaCy's `en_core_web_lg` — local ML
inference, no network call — so the rule as written says Rust, and that is impossible.

**Refined rule:** *does it need a network call to a provider, **or** a Python-only ML
ecosystem? → Python. Everything else → Rust.*

This keeps embeddings in Rust for the right reason (`fastembed-rs` genuinely exists)
and puts Presidio in Python for the right reason (nothing equivalent exists), instead
of a rule that quietly fails on the second subsystem it meets.

**Consequence:** the Python side is not purely a model-call worker — it is a
*Python-ecosystem worker* with two capabilities. `PROTOCOL.md` gains a PII endpoint
when `security/` is ported (`BUILD_ORDER.md` Phase 3, item 3), not before. Same
question will need answering for `detect-secrets`, `faster-whisper`, and
`RestrictedPython` (which stays Python by definition — it sandboxes Python).

---

## D4 — HTTP/JSON, not gRPC, for v0

**Decision:** HTTP/1.1 + JSON. Revisit gRPC when measured serialization cost or
streaming volume justifies it.

The 2026-07-28 boundary ruling already said start with HTTP/JSON where inspectability
matters. It matters unusually much here: the owner's motive is comprehension, and being
able to `curl` a boundary and read the answer is worth more than protobuf's type safety
right now. The schema in `PROTOCOL.md` recovers most of that safety.

---

## D5 — Python owns provider keys

**Decision (owner):** the runtime holds provider credentials. Rust never does.

Secrets stay in one process, and it is the process that makes the calls. The
alternative — Rust injecting keys per request — would make the runtime fully stateless
but puts credentials in the Rust core's memory and on the wire every call. Not worth
it.

---

## D6 — The frontend contract does not change

**Decision (owner):** Rust serves the identical HTTP/SSE surface.

`sse_contract_drift.py` fails on any SSE event the frontend has not declared, and it is
what keeps **CB6 — our only passing Critical benchmark** — green. Keeping the surface
identical means that benchmark keeps enforcing straight through the migration, against
the Rust implementation, for free. Redesigning the API at the same time would remove
the safety net at the exact moment it is most useful.

A worse API that stays verifiable beats a better API that un-proves CB6.

---

## D7 — Contract-first, not Rust-first

**Decision (owner):** build the boundary inside today's Python before any Rust exists.

Two risks are otherwise taken together: *is this boundary right?* and *is this Rust
right?* Contract-first separates them. A boundary mistake then costs a Python refactor
instead of a Rust rewrite. Cost is ~1,150 lines of `core/llm/` becoming a client, which
agents can do without spending the owner's hours.

---

## D8 — Mirrored per-language tests cannot detect drift

**Decision:** one shared scenario file per subsystem, run against both languages, is
the drift detector. Rust-native tests keep a different job.

The owner proposed writing the Rust while agents write Rust-native tests from it, using
the Python tests as reference — *"and that way, we can also know if anything drifted."*
Two-thirds of that is right and kept: agents writing the tests is the correct division
of labour, and the Python tests are a good reference because they encode real
incidents.

**The drift claim is the part that fails.** An agent writing a Rust test reads *the
Rust*. If the Rust is subtly different but self-consistent, the agent writes a test
that matches the Rust and it passes. Confirmation, not detection.

| | Python | Rust | Test written for it | Result |
|---|---|---|---|---|
| reconcile a $0.50 reservation, $0.20 spent | releases **$0.30** | releases **$0.50** | agent reads the Rust, asserts `0.50` | both suites green, money leaks |

Nothing compares the two. Only a shared artifact can.

Rust-native tests still earn their place — panics, ownership, concurrency, error paths
a black-box scenario never sees. They are simply not the drift detector.

---

## D9 — The validation gap is the real risk, not the Rust

33,420 lines of tests import Python modules directly. They cannot validate Rust, so the
core would start with **zero** inherited validation.

This is why agent hours go to the harness rather than to more Python: **the harness is
the schedule, and the Rust is downstream of it.** If it is treated as optional polish,
the migration proceeds with no signal, and that failure is silent until production.

`CONFORMANCE_HARNESS.md` §5 step 0 — forcing each subsystem behind a real port — is
LAW 6 work that improves the Python on its own terms. If the migration paused for a
year, that work would still have been worth doing. Very little else here has that
property, and it is the reason to start there.
