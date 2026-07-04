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

## Backlog (filled by the audit; ranked value × safety)

- [ ] (audit in progress — findings land here, each: file:line · what · why it
      helps modularity/clarity/stability · exact safe fix · risk)

## Known seed items (pre-audit, already spotted)

- [ ] DRY: `HydrationRequest.wiki` is built from `ctx.wiki_entries` with the same
      `tuple((e.get("title",""), e.get("content","")) for e in … if isinstance(e,
      dict))` comprehension in ≥3 places (`core/memory/prefetch.py`,
      `core/orchestrator/loop.py`, `registry/capabilities/handler/tools.py`) — one
      helper, one source of truth.

**Acceptance:** the load-bearing modules pass a re-audit (modular, non-redundant,
documented); suite green; a short "foundation stability audit" section in the
mission report. Then capability work (Phase 5) proceeds on a base we trust.
