# RETURN_BRIEF — start here when you're back

> Your one front door after time away. Foggy-maintainer friendly: each item carries a
> recommendation so your job is approve/reject, not analyze from scratch.
> Written 2026-06-20. HANDOFF.md remains the loop's operating memory; this is the richer
> front door.

## (a) What happened while you were away

The unattended loop cleared the entire v1 test/doc queue: **11 open PRs (#2-#5, #7-#13)**
plus it correctly opened **needs-reviewer issue #6** instead of writing a bogus test when
it hit a stale premise. A senior-engineer review then (1) deep-read the codebase and docs,
(2) filed **5 new needs-reviewer decisions (#14-#18)** for things only you should decide,
(3) wrote a fresh **v2 queue of 8 in-scope tasks** (now live in QUEUE.md), and (4) hardened
the loop's prompt template so every future iteration pins reality, web-checks version
claims, treats docs as a proposal, and writes legible PRs. No code on main changed; no PR
was merged (merges are yours).

## (b) PR merge guide — 11 open PRs (you merge; the bot cannot)

**Merge freely — clean, in-scope, premises verified (8):**
- **#2** docs: fix error docstrings to name real constants (real bug fixed)
- **#3** docs: document `BlockReason.MALFORMED_INPUT` in the enum docstring
- **#5** test: pin `foundation.__all__` against the import block (verified aligned today)
- **#7** test: pin per-layer model settings + usage limits
- **#9** test: pin the sanitizer modality dispatch ladder
- **#10** test: lock invariant A (NETWORK tool output re-sanitization) — high-value
- **#12** test: characterize `_load_one` overlay precedence vs `resolve_overlay`
- **#13** test: pin the shared expert `run()` entry-point contract (introspected all 9 experts, negative-checked, hermetic)

**Reviewed in depth — all three rest on premises that shifted, but the bot navigated each
correctly. Recommendation: MERGE all three (see the inline PR comments I added):**
- **#4** docs(registry) path fix — **MERGE.** The bare `config/prompts.py` resolved to a
  nonexistent `capabilities/config/`; the fix points at the real `registry/config/prompts.py`.
  The bot transparently flagged the doc's pre-existing path-root mixing. Cosmetic only.
- **#8** failure-classifier characterization — **MERGE.** The "two independent classifiers"
  premise is stale (they now share `core/llm/failures.py`), but the bot wrote two
  characterization tables off the *running* code (53 passing) targeting the real consumers.
  Additive, sound.
- **#11** RunState round-trip — **MERGE.** The methods live on `RunStore`, not `RunState`;
  the bot re-targeted correctly and added a field-classification drift guard — exactly the
  silent-drift net for the `run_store` positional-INSERT surface.

**Merge mechanics:** every PR also edits HANDOFF.md (the loop updates it per branch), so
merging several in a row will throw trivial HANDOFF.md conflicts. HANDOFF content is not
load-bearing — resolve by taking either side, or merge and let the last one win.

## (c) needs-reviewer decision queue — your call, with my recommendation

| # | Decision | My recommendation (one-line rationale) |
|---|---|---|
| **#14** | ADR 0004 (§V.21-22 atomic budgets + Postgres RLS) is "accepted" but unbuilt | **Downgrade to proposed + soften the invariant wording to "target."** Most dangerous doc-vs-reality gap; keep the design, stop asserting it as enforced. |
| **#15** | §V.20 / ADR 0002 claim a Semgrep "build-failure" gate that doesn't exist | **Soften wording now ("enforced at runtime via the MemoryPort door"); build the small Semgrep gate as a follow-up.** Cheapest aspirational invariant to make real; runtime scoping is already tested. |
| **#16** | Memory architecture sequencing (5-layer ROBUST + kernel-scale graph) | **Ship typed-knowledge records (§I.3 `EntryType` on the existing store) FIRST, before any graph.** It's additive, unblocks promotion-priority §I.2, demos in <3 min, and is the true prerequisite for the graph. Your owned workstream. |
| **#17** | Normalizer judges media capability against the orchestrator model, not the media route | **Resolve media capability against the `media_expert` role.** Latent correctness bug; low blast radius today. Fix-then-test (do NOT pin the current behavior). |
| **#18** | Rate limiter keys on session id, not user_id/IP (rotatable bypass) | **Key on `user_id` with IP fallback; keep the global window as backstop.** Bounded today (global limiter + demo IP limits), load-bearing once anon traffic scales; same plumbing as §IV.18. |
| **#6** | (loop-filed) Stage-alignment test premise stale: parallel arrays gone | **Close as resolved — no action.** The refactor already moved label/status onto the Stage object; v2 Task 3 fixes the doc references. |

## (d) The in-progress v2 queue (what the loop is building now)

7 tasks, strict scope (additive tests, characterization/regression, doc-staleness only),
ordered so safety nets land before the work that rides on them. Full text + the reasoning
preamble are in QUEUE.md.
1. models.yaml fallback-chain reference-integrity test (drift net)
2. @tool/@expert decorator↔spec field-mirroring characterization (drift net)
3. doc-staleness: mark superseded `_STAGE_LABELS`/`api/runs.py`-god-file refs in docs/suggestions
4. memory hydrate fail-closed without `user_id` (hermetic, §V.20)
5. output filter fail-closed on infra/LLM fault (currently untested)
6. sanitizer pre-gate blocks before any modality worker runs
7. memory hydrate Lagrangian water-filling allocation characterization (hermetic)

(The expert `run()` conformance test originally planned as an 8th task was completed by
the loop as **PR #13** during this prep, so it is not re-queued.)

## (e) Anything else needing your judgment

- **The loop template change is live on next service restart** (you accepted it + added the
  no-AI-attribution rule). It now points each iteration at the QUEUE CONTEXT preamble, so
  your judgment propagates without you in the loop. Loop logic/ledger/safety flags untouched.
- **Nothing else is blocking.** The 6 decisions (the 5 above + the postcss item under
  Security) + the 11 PR merges are the whole of your return review. The loop keeps
  producing PRs against the v2 queue; if it drains it, it sleeps 6h and re-reads — add
  `- [ ] ` lines anytime.

## Security — Dependabot alert (assessed 2026-06-20)

1. **Dependency + CVE.** `postcss` (npm), GHSA-qx2v-qp2m-jg93 / CVE-2026-41305, **moderate
   (CVSS 6.1)**, XSS via unescaped `</style>` in CSS stringify output. **Transitive**, nested
   under Next.js: `frontend/node_modules/next/node_modules/postcss@8.4.31` (`< 8.5.10`). The
   project's top-level postcss is already 8.5.15 (patched); Next 16.2.9 (current latest) pins
   the vulnerable copy **exactly**, so it can't be bumped standalone. Known upstream issue:
   vercel/next.js#93234.
2. **Reachable here? No — dormant.** postcss runs only at BUILD time (Next + Tailwind v4
   compiling first-party CSS). The CVE needs USER-SUBMITTED CSS re-stringified into a runtime
   `<style>` tag; the frontend imports no postcss in `src/` and has no user-CSS-to-`<style>`
   path, so the vulnerable stringify is never fed untrusted input.
3. **Verdict: fix-on-return (near-ignorable).** Recommended: wait for the Next.js release that
   bundles postcss >= 8.5.10 (tracked upstream), then take the Next bump PR; or, to clear it
   now, an npm `"overrides": { "postcss": ">=8.5.10" }` one-liner in `frontend/package.json`
   (frontend agent's domain). Full write-up + recommendation in needs-reviewer issue **#19**.

**Dependabot:** vulnerability alerts and security updates are now **enabled** on the repo, so a
fix PR auto-opens for your review once an upstream patch exists (don't expect one until Next
ships the bump, given the exact pin). It goes through the same review-on-return flow — nothing
to merge now, and the loop did not change any frontend code.
