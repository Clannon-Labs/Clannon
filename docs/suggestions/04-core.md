# core/ (intake, llm, memory, normalizer, orchestrator, verifier)

`core/` is cleanly layered overall — a consistent "stage door vs internals" split, and the
`core/llm` single-SDK seam is intact (the rest of the codebase touches pydantic-ai only
through it). The findings are mostly "the same concept expressed in two places."

A useful **negative** result first: the "force one final answer at the turn/usage cap"
pattern — a duplication suspect — is **not** duplicated inside core. It lives once in
`registry/capabilities/handler/support.py` (`think()` and `_EXPERT_FORCE_ANSWER`,
`support.py:237,290`). The orchestrator loop reuses the same idea via that path rather than
keeping its own copy. Good.

---

<a id="c1"></a>
## C1 — Two independent provider-failure classifiers

- **Severity:** Medium
- **Type:** duplication
- **Locations:** `core/llm/retry.py:32-50` vs `core/orchestrator/utils/recovery.py:27-68`.

**Problem.** Two different ways to answer the same question — "is this exception a transient
provider failure?" `retry.py` classifies structurally (exception types / status codes);
`recovery.py` re-classifies the *same* exception trees by string-matching on messages.

**Why it hurts.** Two divergent idioms for one decision. A new provider error shape (a new
SDK version, a new 5xx variant) must be taught to both, in two different styles, or they
disagree — one retries, the other gives up.

**Suggestion.** One classifier in `core/llm` (e.g. `llm.classify_failure(exc) ->
{transient, rate_limited, fatal}`) that both the retry wrapper and the orchestrator
recovery call. The recovery layer decides *policy* (degrade vs fail); the *classification*
is shared.

---

<a id="c2"></a>
## C2 — Per-layer bounds as parallel `if layer ==` chains

- **Severity:** Medium
- **Type:** duplication
- **Locations:** `core/llm/registry.py:171-216` — `model_settings_for_layer` and
  `usage_limits_for_layer`, two `if layer == …` ladders over the same set of layers.

**Problem.** Two functions each branch on the same layer enum to return that layer's
settings vs its usage limits. The layer set is encoded twice as control flow.

**Why it hurts.** Same "parallel ladders keyed on one thing" pattern as the pipeline
side-arrays. Add or rename a layer and you edit two ladders; miss one and a layer silently
gets default bounds.

**Suggestion.** One table keyed by layer — `LAYER_CONFIG = {layer: LayerBounds(settings=…,
usage=…)}` — and the two functions become one-line lookups. Adding a layer is one row.

---

<a id="c3"></a>
## C3 — Episodic write-policy hardcoded in the orchestrator

- **Severity:** Medium
- **Type:** scattered logic / wrong layer
- **Locations:** `core/orchestrator/orchestrator.py:52-83`.

**Problem.** The orchestrator hardcodes how a memory write is shaped — the content format,
the truncation length, the threshold for whether to write at all. That's memory *policy*
living in the orchestrator.

**Why it hurts.** To change "how/when we persist an episodic memory" you edit the
orchestrator, not `core/memory` — the opposite of where you'd look, and a change that
should be owned by the memory layer is split across two domains. It also means the memory
layer can't enforce or evolve its own write policy.

**Suggestion.** Move the shaping/threshold into `core/memory` (e.g. a
`memory.propose_write(ctx) -> MemoryWriteProposal | None` that owns format, truncation, and
the "is this worth keeping?" decision). The orchestrator just calls it.

---

<a id="c4"></a>
## C4 — `MemoryManager` mixes five concerns

- **Severity:** Low
- **Type:** mixed concern
- **Locations:** `core/memory/manager.py:88-290`.

**Problem.** One class owns hydration, *two* ranking strategies, budget allocation, write
policy, and an admin surface.

**Why it hurts.** Hard to change one ranking strategy or the budget math without reading
the rest; the file is the memory domain's largest and least cohesive.

**Suggestion.** Peel ranking into a `ranking.py` (the two strategies as named functions),
budget into the existing Lagrangian-allocation helper, leave `manager.py` as the
orchestration that composes them behind `MemoryPort`. No behaviour change.

---

<a id="c5"></a>
## C5 — `memory/writer.py` is misnamed

- **Severity:** Low
- **Type:** naming
- **Locations:** `core/memory/writer.py`.

**Problem.** The file is named for "writing" but only *distills* a candidate — it doesn't
own the write path (the store does).

**Why it hurts.** Misleading name: someone looking for "where memories get written" opens
the wrong file. Minor, but it's the kind of thing that makes the codebase less intuitive —
which you explicitly care about.

**Suggestion.** Rename to `distill.py` (or fold into the C3 `propose_write`), so the name
matches what it does.

---

<a id="c6"></a>
## C6 — Verifier consistency-coercion scattered

- **Severity:** Low
- **Type:** scattered logic
- **Locations:** `core/verifier/agent.py:51-114`, `core/verifier/schemas.py`,
  `core/verifier/verifier.py:29-42`.

**Problem.** The logic that coerces the verifier's output into a self-consistent
`VerificationResult` (e.g. reconciling a verdict with its reason/fields) is spread across
the agent, the schema, and the verifier entry.

**Why it hurts.** To change how a verifier result is normalized you touch three files in
one small domain.

**Suggestion.** Centralize the coercion in one place — most naturally a validator/
normalizer on the `VerificationResult` schema, so the agent and entry point just construct
and trust it.

---

## Domain summary

`core/` is the best-layered domain; the issues are "same concept in two places" rather
than structural rot. The three worth doing: a single shared failure classifier in
`core/llm` instead of one structural and one string-matching copy (C1); one layer-config
table instead of two parallel `if`-ladders (C2); and moving episodic write policy out of
the orchestrator into `core/memory` where it belongs (C3). The Low items (memory manager
cohesion, the `writer.py` name, verifier coercion) are cleanups for when you next touch
those files.
