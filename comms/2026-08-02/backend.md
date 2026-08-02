
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

## `specification/` created at the root — frontend, this clears your road

Owner instruction: the frontend must not stall because the backend is migrating to
Rust. New root directory **`specification/`** is the answer, and it is TRACKED
(`proposals/` is gitignored — a request filed there never reaches another machine, so
it could never have carried a contract).

**`docs/` = how it works and why. `specification/` = what must be true.** The split is
there because the Rust rewrite kills implementation docs and leaves contracts standing.

### frontend — the two things that matter to you

1. **`specification/api/ROUTES.md` is now the authority on routes and response
   shapes.** All 38, verified against `backend/api/app.py` on 2026-08-02.
   `frontend/BACKEND_INTEGRATION.md` is **superseded for routes and shapes** — it says
   of itself "complete, authoritative, do NOT read the backend code", and that is no
   longer true for that one question. It remains correct and yours for
   frontend-internal architecture (`ClannonClient`, mock/http split, `src/config/`).
   I have not touched the file; it is your tree.
2. **`specification/api/requests/` is your write channel.** Need a route that does not
   exist? Copy `TEMPLATE.md`, one route per file, commit, drop a line in your comms
   file. I answer **every** request — built, declined with a counter-shape, or blocked
   with the reason. Mock it and keep building; do not idle waiting on me.

**Your contract does not change under the migration** (`specification/rust/DECISIONS.md`
D6). Rust serves the identical HTTP/SSE surface, which is what keeps CB6 green straight
through the rewrite. Build normally.

### everyone — paths moved

`docs/architecture/rust/` → **`specification/rust/`**. `API_SPECIFICATION.md` →
`specification/api/ROUTES.md`; `RUST_IDIOMS_AND_CRATES.md` → `IDIOMS_AND_CRATES.md`.
`git mv`, history intact, no stub left behind (LAW 1). Earlier entries in this file
still name the old paths — they were true when written; this line is the correction.

### one finding worth keeping

The SSE event table I wrote into the spec was **already wrong**: 7 types listed, 10
real (missing `message_done`, `sources`, `usage`). It was a hand copy of something
`sse_contract_drift.py` already checks — an unchecked fourth source that rots while the
suite stays green. Removed and replaced with a pointer to the fixture and
`backend/api/README.md`. **Rule now in CLAUDE.md: never restate what a test checks.**

### the merge is done too — `specification/api/SEMANTICS.md`

`reports/INTEGRATION_CONTRACT.md` moved in (`5bffa37`). **`reports/` is now per-role
folders only.** `ROUTES.md` = what exists, `SEMANTICS.md` = what it means and what the
UI may never claim. Every rule in it is a real incident, not a preference — keep them
when editing.

**frontend, one thing you will want to know:** v1 of that contract closed with five
"frontend alignment requested" items and a "current frontend mismatch" section. **All
five are done** — I verified by reading your code, not by trusting the note. Reducer
handles `verification` (`hooks.ts:408`), seal reads persisted state after terminal
(`hooks.ts:527`), `VerifiedSeal` takes a `state` prop (`verified-seal.tsx:26`), and
`verification-status.tsx` renders all five states distinctly including nothing at all
for `null`. Recorded in §7 so nobody redoes finished work.

Dropped rather than moved: the SSE event/payload table (same unchecked-copy mistake as
above) and the commit changelog (git history holds it).

### still open

- Durable version of the SSE rule: extend `sse_contract_drift.py` to also check the
  spec file, so a stale table fails the suite instead of relying on someone noticing.
  Not done — the rule is currently prose in CLAUDE.md, which is exactly the weaker
  thing the rule itself warns about.
- Owner gate: `proposals/to-owner/2026-08-02_boundary-rule-second-clause.md` (Presidio
  has no Rust equivalent). Does not block Phase 0.
