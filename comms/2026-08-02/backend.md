
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
- Verified before trusting: deep reader tenant scoping is real (`deep_reader.py:245`
  drops and logs a cross-tenant hit; `request.wiki` is scoped upstream at
  `api/app.py:617`). The filter identity fix living only in `prompts.secure/` is
  correct, not drift — the overlay auto-discovers that dir, so it is the text that runs.
