# Clannon unattended loop, task queue (v2)

Each `- [ ] ` line is ONE task the loop attempts in order, on its own feature
branch, opening a PR to main. **Read the CONTEXT below before doing any task**, then
apply the METHOD discipline in the loop prompt (pin reality, verify version-sensitive
claims, treat docs as a proposal). Add more `- [ ] ` lines anytime; the loop re-reads
this file.

---

## CONTEXT (inherit this judgment, do not just run the line)

The v1 queue (docstring fixes + first characterization tests) is **complete** — it
produced PRs #2-#5, #7-#12 and needs-reviewer issue #6, awaiting the maintainer's
review. This v2 queue continues the same mission: **tighten the safety net around the
parts that are already strong, fix docs that now describe deleted code, and lock the
fail-closed behaviors that protect users — without destabilizing anything.**

**SCOPE FENCE (absolute).** Additive tests, characterization/regression coverage of
EXISTING behavior, and pure doc-staleness fixes ONLY. NO security patches, NO prompt
edits (verifier/filter are locked), NO refactors, NO new experts/tools, NO ADR/invariant
edits. Anything that is a *decision* (architecture, security boundaries, invariant
wording) is NOT a task — it lives as a `needs-reviewer` issue (see #14-#18). If a task
would require a code change beyond an additive test or a doc fix, or you find real drift,
open a `needs-reviewer` issue instead of guessing.

**STRENGTHS to protect (never destabilize these):**
- `foundation/transport/flow.py` — the only inter-stage transport. Never route stage
  data outside Flow (Inv §III.11).
- `core/pipeline.py` — `ACTIVE_STAGES` carries name/label/status ON each Stage; it is
  the single source of stage order. Do not reintroduce parallel side-arrays.
- The security spine, ordered `intake -> sanitizer -> normalizer -> verifier ->
  orchestrator -> filter -> delivery` (Inv §IV.14). Pre-sanitization hard-gates; the
  verifier is the sole input blocker; the output filter is the sole output gate and
  fails CLOSED. NETWORK tool output is re-sanitized (Inv §IV.17, tools.py invariant A).
- `core/memory/manager.py` behind `foundation.MemoryPort` — `user_id` mandatory and
  fail-closed (Inv §V.20); experts only PROPOSE writes (Inv §I.6); every fault degrades,
  never fails a run.
- `core/llm/` — the only place the provider SDK lives (Inv §III.12); `failures.py` is
  the single transient/fatal classifier; fallback chains are cross-provider (§VI.24).
- The capability self-registration + guarded handler (`registry/capabilities/`) —
  malformed registers BROKEN, never crashes discovery; the handler enforces every grant,
  permission, timeout, output cap, and the NETWORK re-sanitize.

**ORDERING rationale (earlier tasks de-risk later ones):**
1. Tasks 1-2 first — they net the two hand-synced "parallel list" surfaces (models.yaml
   fallback chains; the @tool/@expert decorator/spec mirror) where a silent typo or a
   missed field rots quietly. Catching drift early protects everything built on top.
2. Task 3 — fix docs that still describe symbols the refactor deleted (`_STAGE_LABELS`,
   the `api/runs.py` god-file). Stale symbol references are exactly what made two v1
   tasks rest on false premises; correcting them stops future iterations chasing ghosts.
3. Tasks 4-6 — pin the fail-closed behaviors that protect users (memory scope, the
   output filter, the sanitizer pre-gate). These are characterizations of existing
   behavior, not new guards.
4. Tasks 7-8 — conformance + one signature-behavior characterization, lower blast radius,
   so they ride on the safety nets the earlier tasks established.

---

- [ ] Add an additive, hermetic test (backend/tests/, mirror existing conventions) asserting every model referenced in a models.yaml `fallbacks:` chain resolves to a model/role actually defined elsewhere in models.yaml, loaded via registry.config.load_model_registry, so a typo that silently drops a fallback is caught. Assert the current config is internally consistent; if a dangling fallback reference already exists today, open a needs-reviewer issue instead of editing models.yaml.
- [ ] Add an additive characterization test (backend/tests/, near orchestrator_registry.py) that the @tool and @expert decorators in registry/capabilities/registration.py copy every spec field they currently mirror from the capability class onto the ToolSpec/ExpertSpec (permission, eager, model_role, tool_grants, skills, timeout_s, and the rest), so adding a spec field without wiring the decorator (or the reverse) is caught as drift. Assert the present mirrored-field set only; do not change the decorator or the specs. If they already diverge, open a needs-reviewer issue.
- [ ] Docs only: docs/suggestions/{00-cross-cutting.md,01-api-delivery.md,05-foundation.md,README.md} still describe deleted symbols (main.py `_STAGE_LABELS`, api/runs.py `_STAGE_STATUS`, the 591-line api/runs.py god-file, RunState/RunStore living in api/runs.py). The refactor already moved stage label/status ONTO each Stage in core/pipeline.py and split api/runs.py into a facade over api/run_driver.py + api/run_state.py + api/run_store.py. Verify each referenced symbol against the current code, then add a concise dated note (e.g. `> Update (2026-06): superseded by the Stage-metadata + runs.py-split refactor; see core/pipeline.py Stage and api/run_{driver,state,store}.py`) at the head of the affected items (X1, A3, the §05 stage-identity paragraph). Do NOT rewrite or delete the historical analysis; only mark what the refactor changed. If a referenced symbol still exists in code, leave it and say so.
- [ ] Add an additive, hermetic characterization test (backend/tests/, no Qdrant or embeddings needed) pinning that core/memory/manager.py MemoryManager.hydrate returns an empty package with the "no user scope" note when HydrationRequest.user_id is empty, and that record_write_proposals is a no-op without a user_id, before any store or embedding call (invariant §V.20 fail-closed). tests/memory_isolation.py is skipped when Qdrant is down, so this branch is currently untested. Assert current behavior only.
- [ ] Add an additive characterization test (backend/tests/, mirror output_filter.py conventions) pinning that the output filter stage fails CLOSED: when filter adjudication raises an infra/LLM fault, security/filter/filter.py wraps it into FilterError and returns flow.fail (the run stops, the draft is NOT delivered), never flow.next. Assert current behavior; do not modify the filter.
- [ ] Add an additive characterization test (backend/tests/, extend sanitizer_runner.py conventions) pinning that a HIGH or CRITICAL pre_sanitization result blocks in security/sanitizers/runner.py BEFORE any modality worker is scheduled (assert no worker scan is invoked when the pre-gate blocks). If this exact ordering is already asserted elsewhere, extend minimally rather than duplicate; do not modify the runner.
- [ ] Add an additive conformance test (backend/tests/) asserting every expert in backend/experts/*/expert.py exposes the shared contract: an async run(self, args, env) -> ExpertOutput with an ExpertEnv-typed env and a per-expert args model. Drive discovery off the registry or filesystem so a newly added expert is covered automatically. Test only; if one expert diverges, open a needs-reviewer issue rather than editing the expert.
- [ ] Add an additive, hermetic characterization test (backend/tests/, monkeypatch core.memory.store.search and embeddings.embed so no Qdrant or model is needed) pinning the Lagrangian water-filling budget allocation in core/memory/manager.py hydrate: per-tier floors are applied first, the remainder is split proportional to each tier's mean rank score, and returned items are sorted by (trust, score) descending. Assert the current allocation for a representative multi-tier hit set; do not change the allocation. If the observed behavior differs from this description, pin what it ACTUALLY does and note the discrepancy in the PR.
