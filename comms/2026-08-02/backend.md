
## dispatched workers
- `00:12` **memory** worker via **codex** — 2026-08-01_deep-memory-reader-and-prompt-depth.md — exit 0, 2005s — output: `.agents/runs/20260801-233853-memory.out`
- `00:15` **frontend** worker via **codex** — 2026-08-01_fixed-billing-and-mock-checkout-contract.md — exit 0, 2375s — output: `.agents/runs/20260801-233616-frontend.out`

## Proposal sweep

- Verified and archived completed API, frontend, memory, orchestration, and security
  proposals. Added standing coordinator rule: sweep every expert inbox without owner
  reminder; proof, not status text, decides archival.
- API archive isolation: exact two-user HTTP proof added; own four tiers visible,
  foreign delete indistinguishable from unknown 404, foreign record preserved.
- Security: identity guard permits denial/quotation/comparison while blocking direct
  and indirect provider claims; both semantic mutations fail.
- Orchestration: central and engineering batch prompts describe exact runtime tools,
  boundaries, mission rules, and call stopping conditions; dynamic surface contracts.
- Memory: scoped post-verifier reader added behind Manager. Real synthetic Haiku proof
  selected only tenant-scoped evidence in 9.45s. Separate 15s reader deadline fixed a
  measured 5s timeout; fast hydration still uses 5s embedding deadline.
- Frontend expert completed fixed billing/mock checkout contract and committed it as
  `e53197f`. Unrelated active template files remain untouched and uncommitted.
- Combined owner proposal stays partial: cheaper-model routing and live A/B quality /
  latency evidence remain unproven and are tracked in ROADMAP.
- Coordinator integration: 301 passed. Full suite stopped for owner pack-up after
  101 passes / 66s, not a failure. Component suites cover changed domains. Invariants:
  7 PASS, one existing NETWORK warning.

## Later session — `0748bbc` re-verified, empty failure reason closed

- Ran the full suite `0748bbc` never got: **1 failed / 1636 passed**. The one failure
  was `orchestrator_ports.py::test_memory_store_and_recall_for_user`, and it was
  environmental, not the commit: the nomic embedding model was cold and the test
  spent 2m21s downloading it from HuggingFace, so the embed timed out. Warm, the
  same file passes in 11s. This is the long-suspected "flaky" memory test — the
  cause is a cold model cache, so it is worth warming embeddings before any suite
  run that judges memory.
- **`foundation/transport/flow.py` — `flow.fail()` could record an empty reason.**
  `str(exc)` is `''` for message-less exceptions, and the live path is a sanitizer
  worker timeout (`security/sanitizers/runner.py:128`): the gate closed correctly and
  the journal could not say why. New `_describe_error()` falls back to the exception
  type name and keeps any real message verbatim. Mutation-checked in both directions.
- **Same defect, second site, NOT mine to fix:** `core/memory/hydration.py:86` logs
  `memory embed degraded (%s)` and printed literally `memory embed degraded ()` during
  the run above. Memory's tree — flagging, not editing.
- `docs/ROADMAP.md` header claimed pydantic-ai was "UNPINNED at 2.18.0" while
  `requirements.txt` pinned and the venv had **2.22.0**. Corrected against the
  installed version, recorded in §6.
## Owner ruling — Rust core + Python model worker (2026-08-02, affects everyone)

**Track B is no longer deferred.** Owner decided the backend splits into
`clannon-core` (Rust: pipeline, memory, tools, experts, orchestration, security,
registry, budgets, **and the API the frontend talks to**) and `clannon-ai-runtime`
(Python: model calls only). Two services, HTTP/JSON, no FFI.

Decisive argument was maintainability, not speed: an agent wrote most of these 30,467
lines, owner's agent hours are finite, and hand-writing the core is how they come to
own the system. Read `docs/ROADMAP.md` §3 before assuming anything about Rust.

- Design (both `[PROPOSED]`): `docs/architecture/rust/CORE_RUNTIME_CONTRACT.md` and
  `docs/architecture/rust/CONFORMANCE_HARNESS.md`. Ratification gate:
  `proposals/to-owner/2026-08-02_rust-core-contract-ratification.md`.
- **frontend:** recommendation is that your contract does NOT change — Rust serves the
  identical HTTP/SSE surface so `sse_contract_drift.py` keeps enforcing through the
  migration. Nothing for you to do yet; flagging so it isn't a surprise.
- **all specialists:** new backend behaviour still lands in Python. The Rust core is a
  port of existing behaviour, validated by diffing against the Python. Do not start
  writing Rust.
- Corrected two docs the ruling made wrong: `RUST_MIGRATION_STRATEGY.md` said Rust
  stays *behind* Python-owned contracts (now reversed) and ROADMAP §3 said Track B was
  deferred and not started.

## Repo moved to the Clannon-Labs org

`origin` is now `https://clannon-bot@github.com/Clannon-Labs/Clannon.git`. Two traps
found while re-pointing it, both worth knowing:

- A global `url.git@github.com:.insteadof = https://github.com/` rewrite silently
  turns a plain HTTPS GitHub URL into SSH, and this machine's SSH key authenticates as
  the **owner**, not the bot. The `clannon-bot@` prefix in the URL is what dodges the
  rewrite and keeps pushes on gh's bot credential. Do not "tidy" it out of the URL.
- The repo had `user.name`/`user.email` in **local** config, which overrode the owner's
  own global identity — every commit from this repo was authored `clannon-bot`
  regardless of who made it. Removed. Agents still get `clannon-bot` from env vars
  (env beats config); the owner now gets `thecybro`. Both verified with `git var`.

- Verified before trusting: deep reader tenant scoping is real (`deep_reader.py:245`
  drops and logs a cross-tenant hit; `request.wiki` is scoped upstream at
  `api/app.py:617`). The filter identity fix living only in `prompts.secure/` is
  correct, not drift — the overlay auto-discovers that dir, so it is the text that runs.

## Rust contract document set complete; commit identity enforced in code

- **Five docs written** under `docs/architecture/rust/`, all `[PROPOSED]`: README,
  PROTOCOL, API_SPECIFICATION, BUILD_ORDER, CONFORMANCE_HARNESS, DECISIONS,
  RUST_IDIOMS_AND_CRATES. Owner's format rule: **points and tables, not essays** —
  rationale lives only in DECISIONS. Keep it that way.
- **Owner rulings settled:** frontend contract unchanged, contract-first, Python owns
  provider keys, structure approved, drift correction accepted.
- **frontend:** confirmed your contract does not change. Rust will serve the identical
  HTTP/SSE surface so `sse_contract_drift.py` keeps enforcing — that benchmark is what
  keeps CB6 green and it now protects the migration too. `API_SPECIFICATION.md`
  documents all 38 routes if you ever want the surface written down in one place.
- **all specialists:** commit identity is enforced in code now — `crew.sh` stamps it
  for both providers, `.githooks/pre-commit` refuses a wrong-identity commit. If a
  commit is refused, read the message; it tells you which case you hit. Codex sessions
  were previously committing as the OWNER; that is fixed.
- **Next agent work: BUILD_ORDER Phase 0** — no Rust in it. Stand up the Python runtime
  behind PROTOCOL, make `core/llm/` a client of it, prove the product runs unchanged.
- One open owner gate: the boundary rule's second clause (Presidio has no Rust
  equivalent). Does not block Phase 0.
