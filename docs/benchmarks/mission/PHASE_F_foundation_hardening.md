# Phase F — Foundation Hardening   STATUS: in progress (2026-07-04)

**Why now:** the Prime Directive (stability before new surface area) made into a
work phase. The big builds — batch architecture, Mission Engine, knowledge-web —
all sit on the same load-bearing modules. Harden them ONCE, so well that we never
revisit them while building new capability.

**Bar (owner, 2026-07-04):** stable + accurate + fast; **modular to the line** —
single source of truth so a change is made in ONE place (beware genuine
exceptions); **zero redundancy**; readable — clear code + docstrings + comments
explaining everything a developer needs; a developer should *love* reading it.
Improve anything that helps without compromising anything. Be careful.

**Discipline (non-negotiable):** audit → rank by (value × safety) → apply the
LOW-RISK / HIGH-VALUE changes incrementally, **behavior-preserving**, suite green
after every commit, one logical unit per commit. No sweeping rewrite; no change
that risks a contract or an invariant. Anything bigger than a clean refactor →
propose, don't force.

**Load-bearing modules (what the new work extends — hardened first):**
`foundation/` (Flow, contracts, vocab) · `registry/capabilities/handler/`
(capability core the batch layer extends) · `core/orchestrator/` (the loop the
batch orchestrators generalize) · `core/memory/` (the sole-broker door the
two-tier model extends) · `security/` (the gate chain).

## Backlog (from a 3-agent audit of the load-bearing modules; verified, ranked)

The codebase is already disciplined (all three auditors noted it — typed error
taxonomy, noqa+reason on broad catches, coerce_to_bytes as the single bytes door,
core/llm/failures.py unifying classification). These are the residual
single-source-of-truth / clarity gaps.

### Done
- [x] DRY: HydrationRequest construction (wiki/session/user extraction) was
      duplicated 4x -> HydrationRequest.for_turn(ctx, normalized) +
      .wiki_pairs(entries); all 4 sites routed through it (incl. the drifted,
      unguarded api/app.py preview site — now guarded). (commit a483453 + this)

### Low-risk, behavior-preserving — DO
- [x] Wire the DEAD single-source constants: store._BREAKER_S ->
      CB_RECOVERY_TIMEOUT_S; orchestrator build_tool_agent(retries=
      ORCHESTRATOR_MAX_RETRIES); writer.py distill retries -> new
      MEMORY_DISTILL_MAX_RETRIES (not the filter's); MEMORY_MAX_ENTRY_CHARS /
      MEMORY_WRITE_MAX_RETRIES annotated PLANNED. (commit bde4e18) — span-id
      length wiring SKIPPED (primitives.py can't import constants; partial wiring
      would split the source — left as-is, low leverage).
- [x] Foundation docstring fixes (the actively-misdirecting ones): errors.py stale
      constant names; BlockReason add MALFORMED_INPUT; is_ready docstring. (commit
      7305ad5). REMAINING (low value): span_id record-local docstrings; the "sauce"
      comment; house-style reason comment on the 3 bare best-effort catches.
- [x] flow.py DRY: Flow._advance(origin, started) for the 4 transition methods +
      PayloadHandle.of(payload) for the 2 construction sites. (commit c7e4054)
- [ ] Shared elapsed_ms(started) (replaces round((monotonic-started)*1000,2) at
      ~6 handler sites + flow._duration).
- [ ] Registry DRY: _unwrap(record) in support.py; store._specs_of(kind) generator
      behind catalog/cards/unavailable; name _REMEMBER_MAX_CHARS.
- [ ] Memory/orchestrator readability: extract _pack_tiers() (water-filling) from
      the ~100-line hydrate; move _CHARS_PER_TOKEN above its use; comment the
      embeddings-down global-abort; name _SUBSTANTIVE_TASK/ANSWER_CHARS,
      _SECONDS_PER_DAY, the degraded-note; drop stale store.search limit default;
      persist_turn_memory use the memory singleton not build_default_ports.
- [ ] Cross-cut: one _clip_error/MAX_STRUCTURED_ERROR_CHARS for the str(exc)[:200]
      copies (file_read/file_write/sandbox); short_trace() for trace_id[:8].

### Propose-first — APPROVED by owner + DONE (each with a test)
- [x] record_write_proposals returns what it PERSISTED (CB1 honesty) — MemoryPort
      contract change; /memory view surfaces ctx.memory_writes_persisted. (0e3ff74)
- [x] Bound the write path with MEMORY_WRITE_TIMEOUT_S — a stalled store degrades
      instead of hanging the delivered path (symmetric with the read deadline). (0e3ff74)
- [x] discover() import-fault isolation — one module raising at import no longer
      takes down the roster; failures recorded in import_failures(). (4418f99)

### Still propose-first — NOT done (need their own pass)
- [ ] Real span_id wiring into records; current_stage advancing in Flow.next/warn
      (stuck at INTAKE); SSE event-type enum + run_driver emit helpers (FE-contract
      surface); env-var central registry (ops surface).

## Reviews (Phase 6 gate on the contract-touching changes)

2026-07-04, on the write-door + MemoryPort + discover() commits (a483453~1..HEAD):
- **security-review: PASS** — user_id fail-closed intact, no phantom writes,
  single-door preserved, discover() isolation can't half-register a capability;
  noted the timeout under-reports (safe) rather than over-reports.
- **architecture-boundary: PASS** — foundation still imports nothing upward,
  all new imports point down, protocol/impl signatures match, no new coupling.

**Remaining low-risk backlog (next pass):** elapsed_ms helper; registry _unwrap /
_specs_of / _REMEMBER_MAX_CHARS; manager _pack_tiers extraction + constant moves +
_SUBSTANTIVE/_SECONDS_PER_DAY naming + persist_turn_memory singleton; the
str(exc)[:200] clip helper. All behavior-preserving; see backlog above.

**Acceptance:** the load-bearing modules pass a re-audit (modular, non-redundant,
documented); suite green; a short "foundation stability audit" section in the
mission report. Then capability work (Phase 5) proceeds on a base we trust.
