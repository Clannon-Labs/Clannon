# Central `config/` — Phase 1 Discovery: Inventory + Proposed Layout

**Status: D1–D6 RULED by the owner (2026-07-05) — Phase 3 IN PROGRESS.** The rulings are
recorded in `reports/DECISIONS_FOR_OWNER.md`. Layout below is approved. Externalization is
proceeding one area per commit, behavior-preserving (each default equals today's value):
- ✅ **budget** — `config/backend/budget.yaml` + the typed loader `backend/settings.py`
  (`SPEND_CEILING_FRACTION=0.80` single-source per D2, + the api/ history-budget knobs).
- ⏳ next: fold the premature `backend/config/business.yaml` into `tiers.yaml`/`models.yaml`
  and delete it (D6); the `foundation/` product-knob move (D1); then memory/orchestrator/
  tools/security/llm/copy; the memory-tree budget knobs (`_DEFAULT_BUDGET_TOKENS`,
  `_CHARS_PER_TOKEN`) migrate into `budget.yaml` via a memory-agent slice (their tree).

_(Original Phase-1 discovery map + the D1–D6 decision text follow, kept for the record.)_

Method: two full sweeps (backend, excluding `foundation/`+`flow`; frontend, read-only) + backend-agent
recon. Every value below is a hardcoded literal a human might reasonably want to tune. Program logic,
control flow, secrets (API keys), and enum/index constants are excluded.

---

## ‼️ DECISIONS I NEED FROM YOU (these shape the layout — please rule before I build)

**D1 — The `foundation/` boundary (the big one).** You excluded `foundation/`, but
`foundation/vocab/constants.py` is where a large share of the product knobs your spec explicitly
lists as *in scope* actually live — **orchestrator max-turns/timeouts, whole-turn wall clock,
verifier/filter retries, memory read/write timeouts + top-K + relevance floor, the intake rate
limits, LLM-retry backoff, sanitizer timeouts, and the input-size caps.** These aren't transport
internals — they're dials. Three options:
  - **(a) [my recommendation]** Move the *product-tunable* constants OUT of `foundation/vocab/constants.py`
    into `config/backend/*.yaml`, leaving `foundation/` with only genuine transport/contract vocab
    (Flow shapes, error taxonomy, enums). `foundation` code reads them from the config loader.
  - (b) Keep them in `foundation/` and have `config/` *reference/mirror* them (two homes — weaker).
  - (c) Honor the exclusion literally: those stay hardcoded in foundation, and `config/` covers only
    the non-foundation tunables. (This leaves major knobs un-tunable — contradicts the "one place" goal.)
  I recommend **(a)**; it's the only option that fully delivers "one place to change any tunable." It
  does touch `foundation/`, which you excluded — so I will not do it without your explicit yes.

**D2 — The spend/margin ceiling.** There is **no `SPEND_CEILING_FRACTION` (or any margin ceiling)
in the code today.** I'll *create* it as the single-source value in `config/backend/budget.yaml`,
read by the budget enforcement (this is the hinge to the Redis/budget phase). Confirm the value +
that it lives here as the one source.

**D3 — Frontend config home.** The frontend *already* has a mature `src/config/` (theme colors
single-sourced, plans backend-authoritative). Does root `config/frontend/*.yaml` become the new
home (the frontend agent migrates its `src/config` to read from it), or does root `config/frontend/`
hold only the values the **backend** defines + enforces, leaving pure-frontend cosmetics in the
frontend's own tree? Either way I **define the data + backend enforcement; the frontend agent wires
the UI** (via a non-waking proposal, per your spec — I won't touch `frontend/`).

**D4 — Copy scope.** How far to externalize user-facing strings? Safe: role labels, failure/throttle
messages, media notices. **Careful:** capability `description`/`label` strings double as the LLM tool
catalog (semi-structural — changing them changes model behavior, not just display). Marketing copy is
frontend. Tell me if copy is in-scope now or a later pass.

**D5 — Code-embedded model IDs.** The embedding model (`nomic-embed-text-v1.5`) and Whisper size
(`base`) are hardcoded in code, NOT in `models.yaml`. Move them into `config/models.yaml` so *all*
model choices are in one place? (Recommend yes.)

**D6 — My premature `backend/config/business.yaml`.** It's a wrong-located, too-shallow first draft
(plans/limits/model-catalog). Plan: fold its values into the proper `config/backend/tiers.yaml` +
`config/backend/api.yaml` + `config/models.yaml` during Phase 3 and delete it. Say the word if you'd
rather I revert it now for a clean slate.

---

## Proposed root `config/` layout (shaped from what was found)

```
config/
  README.md                     how it works · the backend-vs-frontend authority rule · how to tune safely
  models.yaml                   ALL model IDs + per-role routing + fallbacks (+ embed + whisper, per D5)
  backend/                      backend-controlled — server-enforced, NEVER frontend-changeable
    budget.yaml                 spend ceiling (D2, single-source) · hydration budget · char/token · history budget
    orchestrator.yaml           max turns · timeouts · wall-clock · entropy temp+bands · degraded confidence
    memory.yaml                 tier trust/floors · recency · accept/dedup/supersession bars · content caps · hops · embed dims
    experts.yaml                media caps (doc/PDF/whisper/video/inline) · per-expert model_role
    tools.yaml                  per-tool timeouts/caps · sandbox image+resource caps · chart geometry
    security.yaml               scrypt · session TTL · body cap · auth rate · headers (HSTS/CSP) · ClamAV/YARA · filter caps · verifier excerpt · exec flags
    llm.yaml                    malformed-retry budget · cache size/layers · rate-limit markers
    api.yaml                    ops/deployment (warmup/drain · preview · CORS · cookies · DB · version) — mostly env-driven
    tiers.yaml                  plan/tier definitions + what each unlocks (from my draft business.yaml)
    copy.yaml                   role labels · failure/throttle/media messages (per D4)
  frontend/                     ONLY harmless user-facing tunables (D3; frontend agent wires the UI)
    theme.yaml                  radii · prose type scale · font-timing tokens (colors already single-sourced)
    timings.yaml                animation/interaction durations + easings
    display.yaml                item caps · char/truncation limits
    copy.yaml                   marketing arrays · status/label maps · placeholders
    defaults.yaml               feature toggles · default selections · ordering · legal/compliance values
```
DEEP by design — split any file further if it grows. Every value gets an inline comment (what · unit ·
safe range · why backend-controlled). Loader: typed (pydantic for backend), validate-at-startup,
fail-loud on an invalid value.

---

## Backend inventory (by target file · classification: all BACKEND-CONTROLLED unless noted)

### → `config/models.yaml`
`models.yaml` (root): full per-provider/role catalog + `defaults:` + `fallbacks:` — already externalized.
`registry/config/models.py:24,160` default-provider env + hardcoded `"google"` last-resort ·
`api/config.py:85-90` `qualify_model` prefix→provider · `api/config.py:136-144` `_ROLES` (user-selectable
role→options + **locked** verifier/filter) · **code-embedded (D5):** `core/memory/embeddings.py:20` nomic
embed id + `:21` DIMS 768 · `experts/media/preprocess.py:55` whisper `base`.

### → `config/backend/budget.yaml`
`core/memory/manager.py:72` `_DEFAULT_BUDGET_TOKENS` 2000 · `:80` `_CHARS_PER_TOKEN` 4 ·
`api/run_driver.py:103` `_HISTORY_CHAR_BUDGET` 200000 · `:168` `_VERBATIM_TURN_FLOOR` 2 · **NEW (D2)**
`SPEND_CEILING_FRACTION` (create). Per-plan `tokenBudget` lives in tiers.yaml.

### → `config/backend/orchestrator.yaml`
`core/orchestrator/routing.py:35` `_DEFAULT_TEMPERATURE` 0.1 ("to be tuned") · `:177,179` entropy bands
0.34/0.67 · `core/orchestrator/utils/recovery.py:97` degraded confidence 0.1 · **foundation (D1):**
`ORCHESTRATOR_TIMEOUT_S`, `ORCHESTRATOR_MAX_TURNS`, `ORCHESTRATOR_MAX_TOKENS`, `TURN_WALL_CLOCK_S`.

### → `config/backend/memory.yaml`
`core/memory/manager.py`: `_TIER_TRUST` (60-63), `_TIER_FLOOR` (66-71), `_RECENCY_HALF_LIFE_S` 30d (75),
`_RECENCY_FLOOR` 0.5 (76), `_MIN_ACCEPT_CONFIDENCE` 0.6 (77), `_DEDUP_SIMILARITY` 0.97 (78),
`_MAX_CONTENT_CHARS` 2000 (79), `_SUPERSESSION_FLOOR` 0.85 (87), `_SUPERSESSION_TIMEOUT_S` 5.0 (99) ·
`embeddings.py` `_RETRY_AFTER_S` 60 · `store.py:60` Qdrant timeout 5 · `graph_store.py:47`
`MAX_HOPS_CEILING` 20 · `config.py` env: `QDRANT_URL`, `MEMORY_DISABLED`, `GRAPH_DISABLED`, cache/paths ·
**foundation (D1):** `MEMORY_READ/WRITE_TIMEOUT_S`, `MEMORY_SEARCH_TOP_K`, `MEMORY_RELEVANCE_FLOOR`,
`MEMORY_DISTILL_MAX_RETRIES`, `CB_RECOVERY_TIMEOUT_S`.

### → `config/backend/experts.yaml`
`experts/media/preprocess.py`: `_MAX_DOC_CHARS` 50000 (35), `_MIN_PDF_TEXT` 50 (36), `_PDF_RENDER_DPI`
150 (37), `_MAX_PDF_RENDER_PAGES` 8 (38), whisper model/cache (55-56), `_MAX_TRANSCRIPT_CHARS` 50000 (57),
`_MAX_VIDEO_FRAMES` 8 (59), `_FFMPEG_TIMEOUT_S` 90 (60), whisper device params (117) ·
`experts/media/expert.py:81` `_INLINE_LIMIT_BYTES` 15MB · per-expert `model_role` (writer/documentation→
planner, code/data_analysis→code, notification/summarization→research, media→media_expert).

### → `config/backend/tools.yaml`
`web_search.py:32` timeout 75 + `:31` eager · `code_run.py:38` timeout 300 · `file_read.py:13` `_MAX_READ`
40000 · `diff.py:16` `_MAX_CHARS` 200000 + `:45` context_lines 3 · `http_request.py:30` `_MAX_HEADERS` 25 ·
`fetch_url.py:29` `_MAX_REDIRECTS` 5 · `memory_search.py:28` max_results 8 (1-20) · `chart.py:19-23,42+`
geometry + palette · **sandbox** `registry/capabilities/handler/sandbox.py`: image `python:3.12-slim` (39),
`_MAX_OUTPUT` 20000 (40), run timeout 60 (41), create timeout 180 (42), resource caps `512m/1cpu/256pids`
(134), tmpfs 64m (135), teardown 20 (162), `_ENABLE` flag (37) · `specs.py:71` per-tool `timeout_s`
default→`TOOL_TIMEOUT_S` (foundation, D1: also `TOOL_MAX_OUTPUT_BYTES`, `FETCH_MAX_RESPONSE_BYTES`).

### → `config/backend/security.yaml`
`api/auth.py:24` scrypt `n=2^14,r=8,p=1` + salt 16 · `api/config.py:52` session TTL 14d · `:67` body cap
32MB · `:70-71` auth rate 60s/10 · `api/hardening.py:42-46` HSTS/CSP/security headers ·
`security/sanitizers/pre_sanitization.py` ClamAV host/port/timeout (34-35,75), YARA dir/flags (36,41-42) ·
`security/filter/filter.py:35-38` findings 8 / 1500ch / tool-calls 12 / 1200ch · `core/verifier/constants.py:18`
`VERIFIER_EXCERPT_CHARS` (min 8000, MAX_TEXT_INPUT_CHARS) · `tools/python_exec.py:73` exec opt-in flag ·
**foundation (D1):** `VERIFIER_TIMEOUT_S/MAX_TOKENS/MAX_RETRIES`, `FILTER_MAX_RETRIES/REVISIONS`,
`RATE_LIMIT_*`, `GLOBAL_RATE_LIMIT_*`, `SANITIZER_TIMEOUT_*`, `SANITIZER_MAX_WORKERS`.

### → `config/backend/llm.yaml`
`core/llm/framework.py:63,92` retries 2 · `core/llm/registry.py:129` `_RESOLVED_CACHE_MAX` 64 · `:173`
message-cache layers · `:196-207` anthropic cache flags (per-role overridable in models.yaml) ·
`failures.py:6-14` rate-limit marker strings · **foundation (D1):** `LLM_TRANSIENT_MAX_RETRIES`,
`LLM_RETRY_BASE/MAX_DELAY_S`, `LLM_FALLBACK_MAX_RETRIES`.

### → `config/backend/api.yaml` (ops/deployment — many already env-driven)
`api/app.py:50-51` warmup/drain 30/10 · `:551-552` preview 8 items / 3 min chars · `_health.py:45` sqlite 2 ·
`run_state.py:202` SSE poll 0.02 · `run_store.py:68,82` title trunc 64 · `config.py` VERSION, FRONTEND_ORIGIN,
CORS, cookies, DB_PATH, DEFAULT_PLAN · `config_validation.py:69-70` strict flags · `core/artifacts.py:17-18`
artifacts dir + name cap 200.

### → `config/backend/tiers.yaml`
Plans (id/name/monthlyUsd/tokenBudget/memoryTiers/features) — from my draft `business.yaml`. FEATURES flags.

### → `config/backend/copy.yaml` (per D4)
`api/config.py:137-143` role labels+descriptions (7) · `recovery.py:56-64` failure explanations (3) ·
`rate_limiter.py:126,132` throttle messages · `experts/media/expert.py:88,93,111` media notices ·
`hardening.py:127` "Request body too large." · capability `description`/`label` (⚠ = LLM tool catalog).
Prompts already externalized (`prompts/` + `prompts.secure/`, registry-indexed) — leave as-is.

**Excluded (correctly):** provider API-key env names (`GOOGLE/ANTHROPIC/OPENAI_API_KEY` — secrets),
`_ZERO_NORM_EPS` (numeric logic), enum/index constants.

---

## Frontend inventory (by target file · classification per value)

Frontend already single-sources colors (`theme.config.ts`) and treats plans as backend-authoritative
(`useEffectivePlans()` overrides from `/config`). Genuinely scattered, and their classification:

- **`config/frontend/theme.yaml` (frontend-exposed):** radii scale (`globals.css:48-56`), font stacks
  (44-46) + webfont families (`layout.tsx:9-26`), animation tokens (58-72), grain opacity (265-278),
  glass blur (590-592), report prose measure/size/leading (401-433), scrollbar (249-256).
- **`config/frontend/timings.yaml` (frontend-exposed):** house easings + reveal margins (`motion.tsx:33-36`),
  gesture durations (49-187), toast dismiss (`toast.tsx:53`), dialog close (`dialog.tsx:8`), brief debounce
  (`hydration-panel.tsx:294`), clock tick + settle (`run-activity.tsx:59,159`), SSE reconnect backoff
  (`hooks.ts:305-306`), demo pacing (`hero-demo.tsx`).
- **`config/frontend/display.yaml` (frontend-exposed EXCEPT the input caps):** recent-runs 5, recap 4,
  toast stack 3, hero window 6, filename trunc 60. ⚠ **Input caps must be backend-enforced too:** wiki
  title `maxLength 120` (`memory/page.tsx:498`), project name `maxLength 80` — a bypassed client can
  exceed these; needs a **backend validation** (D3, the "frontend proposes, backend disposes" rule).
- **`config/frontend/copy.yaml` (frontend-exposed):** marketing arrays (FAQS/STAGES/TIERS), status-label
  maps (`run-status`, `expert-panel`, `decision-log`), provenance/placeholder strings, `BRAND_CASING`.
- **`config/frontend/defaults.yaml`:** feature toggles (billing/demo — *mirror* backend FEATURES),
  default API mode, auth provider order, brand icon/wordmark, nav order, theme default. **Legal/compliance
  (backend-authoritative, mirror to UI):** minimumAge 16, deletionWindowDays 30, refundWindowDays 14,
  refundUsageCeilingPct 10 (`site.config.ts:58-76`).

**⚠ 4 duplication drift-risks to fix (frontend mirrors backend, never a 2nd source):**
1. `faq.tsx:19` — plan token numbers baked into FAQ prose (won't follow a backend plan change). 
2. `opengraph-image.tsx:21-50` — dark-theme hex duplicated (edge runtime can't import CSS vars).
3. `manifest.ts:11-12` — theme color duplicated. 
4. `plans.ts` — guarded (overridden from `/config`) but still a duplication surface to watch.

---

## The security classification, in one line
Everything under `config/backend/` is **backend-controlled**: server-enforced, never accepted from the
client. `config/frontend/` holds only harmless cosmetics the user is *supposed* to change — and for the
two input caps (wiki title, project name) that a bypassed client could violate, the value is mirrored to
the UI but **enforced backend-side**. No backend-authority value is ever moved to the frontend.

---

## Next
**Awaiting your ruling on D1–D6.** On approval I proceed to Phase 3: build the typed loader, then
externalize ONE area per commit, each behavior-preserving (default == today's value) with the suite
green, starting with the lowest-risk areas (tools, experts) and treating budget-ceiling / security /
memory-scoping as explicit propose-first contract changes. Nothing moves until you say go.

---

## Phase 3.5 — LONG-TAIL discovery (still-hardcoded, beyond the first pass)

**Why this pass exists.** The owner's standing goal is *"one place to change literally anything
non-code in the product."* The first pass mapped the obvious dials; this pass swept the WHOLE repo
again for the SMALL still-hardcoded knobs it skipped — per-LLM-call cost caps, backpressure/circuit-
breaker/dead-letter limits, media-duration caps, distillation token budgets, security-scoring weights,
truncation lengths, and the frontend's long tail. **Net-new tunables found: ~140** — counting rule:
each BACKEND `file:line` bullet as one (~115 backend), and the frontend's near-identical cosmetics
bundled by classification into ~21 groups (deliberately NOT expanded into 40+ padding lines — e.g.
the theme color system is dozens of tokens shown as one group). So the figure is honest-but-fuzzy, not
a precise item count. Grouped below by target config file. Method: five parallel area-sweeps + a direct read of
`foundation/vocab/constants.py` and `foundation/{transport,contracts}/**` (only contract field
defaults there — nothing tunable) and `core/budget/` (already fully config-driven — nothing hardcoded).
Everything already in `CONFIG_INVENTORY.md`'s first pass or already in `config/*.yaml` is excluded.

> **Biggest single miss: `foundation/vocab/constants.py` itself.** The first pass tagged only *some* of
> its constants under D1 (orchestrator/memory/verifier/tools/llm timeouts). **28 more live constants in
> that one file were never listed** — all product dials, all D1 "move OUT into config/" material. They
> are the highest-value block here.

### → `config/backend/orchestrator.yaml`
- `foundation/vocab/constants.py:138` · `ORCHESTRATOR_MAX_RETRIES = 2` · malformed-output retries before ERROR (first pass listed TIMEOUT/MAX_TURNS/MAX_TOKENS, not this) · **BACKEND**
- `core/orchestrator/loop.py:106` · `_CHAT_REPLY_MAX_CHARS = 600` · a tool-free answer ≤600 chars renders as a chat bubble, longer → deliverable card · **AMBIGUOUS** (product UX channel threshold)
- `core/orchestrator/orchestrator.py:65` · `_SUBSTANTIVE_TASK_CHARS = 40` · min task length for a turn to count "substantive" (worth episodic write) · **AMBIGUOUS** (memory-noise gate)
- `core/orchestrator/orchestrator.py:66` · `_SUBSTANTIVE_ANSWER_CHARS = 200` · min answer length for the same gate · **AMBIGUOUS**
- `core/orchestrator/orchestrator.py:100` · `record.decision[:500]` · cap on DECISION-record content written to episodic memory · **AMBIGUOUS**
- `core/orchestrator/orchestrator.py:190` · `task[:200]` / `response.text[:500]` · caps on the episodic memory note's task/answer text · **AMBIGUOUS**
- `core/orchestrator/utils/recovery.py:32` · `_PER_FINDING_CHARS = 4000` · per-finding chars surfaced in a degraded answer · **AMBIGUOUS**
- `core/orchestrator/utils/recovery.py:33` · `_MAX_FINDINGS = 6` · max partial findings surfaced in a degraded answer · **AMBIGUOUS**
- `core/normalizer/builders.py:132` · `target_layer = "orchestrator"` default · default routing layer for normalization · **AMBIGUOUS** (routing default)
- `core/normalizer/builders.py:172` · `target_layer = "media_expert"` · role image/audio/video route to for native-support judging · **AMBIGUOUS** (routing default)
- `core/llm/search.py:86` · `layer = "search"` default · which model role grounded search uses · **AMBIGUOUS** (role default)
- `api/config.py:112` · `or "research"` · default model role when an expert declares none (dup of specs.py default below) · **AMBIGUOUS**

### → `config/backend/experts.yaml`
- `foundation/vocab/constants.py:160` · `EXPERT_TIMEOUT_S = 240.0` · per-expert invocation wall clock · **BACKEND**
- `foundation/vocab/constants.py:163` · `EXPERT_MAX_CONCURRENT = 3` · max experts running in parallel per orchestrator turn · **BACKEND** (concurrency/resource)
- `foundation/vocab/constants.py:165` · `EXPERT_MAX_OUTPUT_TOKENS = 4096` · per-expert output token cap · **BACKEND** (cost)
- `foundation/vocab/constants.py:166` · `EXPERT_MAX_TURNS = 8` · max tool rounds inside one expert's run · **BACKEND** (cost/latency)
- `registry/capabilities/handler/experts.py:30` · `_MAX_ARTIFACTS = 20` · max output artifacts captured per expert run · **BACKEND** (resource)
- `registry/capabilities/handler/experts.py:31` · `_MAX_ARTIFACT_BYTES = 10 * 1024 * 1024` · per-artifact size cap (10 MB) · **BACKEND** (resource)
- `registry/capabilities/handler/experts.py:32` · `_NEED_CONTEXT_MAX_ITEMS = 5` · cap per need-context recall so one request can't flood expert context · **BACKEND** (context-flood)
- `experts/media/preprocess.py:58` · `_VIDEO_FRAME_EVERY_S = 5` · sample one frame every N seconds of video (distinct from the listed `_MAX_VIDEO_FRAMES`) · **BACKEND** (cost driver)
- `experts/media/preprocess.py:163` · ffmpeg `-ac 1 -ar 16000` · whisper audio downmix to mono/16 kHz · **AMBIGUOUS** (transcription preprocessing param)
- `experts/web_research/expert.py:34` · `eager = True` · puts web-research expert in the orchestrator's eager surface · **AMBIGUOUS** (hot-path ordering/cost)
- `experts/writer/expert.py:37` · `eager = True` · same for the writer expert · **AMBIGUOUS**
- `registry/capabilities/specs.py:89` (+ `registration.py:88`) · `model_role = "research"` default · fallback model-role for any expert that declares none · **AMBIGUOUS**

### → `config/backend/tools.yaml`
- `foundation/vocab/constants.py:147` · `TOOL_SANDBOX_TIMEOUT_S = 25.0` · sandbox process must exit before the tool timeout (first pass listed TOOL_TIMEOUT_S, not this) · **BACKEND**
- `foundation/vocab/constants.py:148` · `TOOL_MAX_RETRIES = 2` · retries on transient sandbox errors · **BACKEND**
- `tools/memory_search.py:29` · `max_results ... le=20` · **hard upper bound** on memories returned (default 8 was listed; the 20 ceiling was not) · **BACKEND**
- `registry/capabilities/handler/support.py:334` · `_REMEMBER_MAX_CHARS = 2000` · size cap on one persisted memory fact/preference · **BACKEND** (write-size)
- `registry/capabilities/handler/support.py:369` · `_RECALL_MAX_HITS = 3` · full turns returned per session recall · **BACKEND** (context-flood)
- `registry/capabilities/handler/support.py:352` · `confidence = 0.95` · fixed confidence on the orchestrator `remember` write; clears the memory write-policy floor · **AMBIGUOUS** (persistence gate)
- `registry/capabilities/handler/support.py:415` · `_DEFER_LONG_TAIL = False` · feature flag for deferred (tool-search) capability loading; affects context size/cost · **AMBIGUOUS** (feature flag)
- `registry/capabilities/handler/tools.py:157` · `blob[:1000]` · truncated tool-output preview length · **COSMETIC**

### → `config/backend/memory.yaml`
- `foundation/vocab/constants.py:198` · `MEMORY_MAX_ENTRY_CHARS = 10_000` · PLANNED (not yet wired; manager caps at its own `_MAX_CONTENT_CHARS`) · **BACKEND**
- `foundation/vocab/constants.py:199` · `MEMORY_WRITE_MAX_RETRIES = 3` · PLANNED (write path not retry-bounded yet) · **BACKEND**
- `core/memory/writer.py:36` · `_MAX_FINDING_CHARS = 1000` · per-finding truncation before distillation · **BACKEND** (LLM input/cost)
- `core/memory/writer.py:37` · `_MAX_FINDINGS = 5` · max findings included in the distill prompt · **BACKEND** (cost)
- `core/memory/writer.py:38` · `_MAX_OUTPUT_TOKENS = 700` · distiller max output tokens · **BACKEND** (cost)
- `core/memory/writer.py:67` · `_MAX_SUPERSESSION_CONTENT_CHARS = 1500` · new/existing content sent to the supersession judge · **BACKEND** (cost)
- `core/memory/writer.py:68` · `_SUPERSESSION_MAX_OUTPUT_TOKENS = 200` · supersession judge max output tokens · **BACKEND** (cost)
- `core/memory/writer.py:104,154` · `max_turns = 1` (distiller + judge) · single-turn each; a raised value multiplies LLM cost · **BACKEND** (cost)
- `core/memory/writer.py:34` · `_MAX_TASK_CHARS = 1200` · **DEAD** — defined, never referenced (task passed unsliced). A distillation-cost knob if wired, else LAW-1 dead code · **AMBIGUOUS / flag**
- `core/memory/writer.py:35` · `_MAX_ANSWER_CHARS = 3500` · **DEAD** — same (answer passed unsliced) · **AMBIGUOUS / flag**
- `core/memory/writer.py:44` · distilled `confidence` default `0.0` · interacts with the `_MIN_ACCEPT_CONFIDENCE 0.6` acceptance gate (bounds 0–1 are contract-fixed) · **AMBIGUOUS**
- `core/memory/writer.py:49` · `kind = "assumption"` default · default epistemic type for a distilled memory · **COSMETIC** (policy default)
- `core/memory/manager.py:349,466` · `store.search(..., 1)` · dedup lookup hardcodes top-K=1; a near-duplicate ranked 2nd is missed · **AMBIGUOUS** (dedup sensitivity)
- `core/memory/store.py:27-32` · collection names `vraksha_{wiki,semantic,episodic,procedural}` · hardcoded, not env/config-driven; a collision mixes/orphans tenant data · **BACKEND** (infra naming — propose-first)
- `core/memory/store.py:112` · `qm.Distance.COSINE` · vector distance metric for every collection; changing it silently invalidates existing vectors' ranking · **BACKEND** (index tunable — propose-first)
- `core/memory/graph_extract.py:49` · `breaks_if_removed(..., max_hops=20)` · a SECOND hardcoded `20`, distinct from `graph_store.MAX_HOPS_CEILING` — two copies that can drift · **BACKEND / flag**
- `core/memory/graph_extract.py:31` · `_EXCLUDE_DIRS = {".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".git"}` · dirs skipped by the code-graph walker; a `venv/`/`env/` project gets walked in · **AMBIGUOUS**
- `core/memory/{graph_extract.py:41,45 · graph_store.py:262,267 · graph_manager.py:85,88}` · `max_hops = 1` defaults · default traversal depth, duplicated across three graph layers · **AMBIGUOUS** (small; DRY flag)
- `core/memory/graph_store.py:246` · edge `"origin": "inferred"` default · governs the "asserted always wins" override; magic string duplicated with `mission_graph_store.py` · **AMBIGUOUS / flag**

### → `config/backend/security.yaml`
- `foundation/vocab/constants.py:211` · `CB_FAILURE_THRESHOLD = 5` · consecutive failures before a circuit trips OPEN (first pass listed only RECOVERY_TIMEOUT) · **BACKEND**  *(→ see resilience.yaml note)*
- `foundation/vocab/constants.py:213` · `CB_SUCCESS_THRESHOLD = 2` · successes in HALF_OPEN before CLOSED · **BACKEND**  *(→ resilience.yaml)*
- `core/verifier/rules.py:31-107` · `INJECTION_RULES` weights (ignore_instructions=4, role_redefinition=4, prompt_exfiltration=5, tool_abuse=4, credential_theft=5, malware_intent=4, instruction_boundary_marker=3) · deterministic injection-risk scores fed to the LLM verifier · **BACKEND** (security-scoring — propose-first)
- `security/sanitizers/workers/text.py:62-76` · `PII_REDACTED_ENTITIES` (13-entity list) · which PII types Presidio redacts; dropping one leaks that PII into reasoning · **BACKEND** (security policy — propose-first)
- `security/sanitizers/workers/text.py:128` · `language = "en"` · Presidio pinned to English; non-English PII undetected · **AMBIGUOUS** (security coverage)
- `security/sanitizers/workers/pdf.py:30-41` · `DANGEROUS_PDF_KEYS` (10-key set: `/JavaScript`, `/Launch`, `/OpenAction`, `/EmbeddedFile`, …) · active-content PDF keys stripped; removing one admits active content · **BACKEND** (security policy — propose-first)
- `security/filter/filter.py:81` · `sources[:20]` · cap on source URLs in the filter's grounding view · **BACKEND** (grounding completeness)
- `security/filter/filter.py:84` · `memory[:10]` + `[:300]` per item · memory-grounding entries + per-entry chars shown to the filter · **BACKEND**
- `security/filter/filter.py:74` · `"recipient": "the same single authenticated user…"` · load-bearing config string driving "don't block the user's own data echoed back" · **BACKEND** (behavioral — propose-first)
- sanitizer threat-severity classes (a retunable policy): `text.py:138` PII→MEDIUM, `text.py:173` secrets→HIGH, `pdf.py:150` huge-page→HIGH, `pdf.py:228` stripped-active-content→MEDIUM, image/audio/video metadata-strip→LOW, `filter.py:117` filter block→MEDIUM · **AMBIGUOUS** (security policy)
- `api/app.py:161` · signup name `min_length=2, max_length=80` · **BACKEND** (input bound)
- `api/app.py:163` · signup password `min_length=8, max_length=256` · **BACKEND**  *(duplicated at `api/auth.py:139` `len(password) < 8` — two sources of truth; LAW-1 flag)*
- `api/app.py:215` · project create name `min_length=1, max_length=80`, color `max_length=24` · **BACKEND**
- `api/app.py:218` · project `seedFacts max_length=20_000` · **BACKEND**
- `api/app.py:222` · project rename `min_length=1, max_length=80` · **BACKEND**
- `api/app.py:395` · run feedback comment `max_length=2_000` · **BACKEND**
- `api/app.py:511-512` · memory entry `title max_length=120`, `content max_length=20_000` · **BACKEND** (backend enforcement of the wiki-title cap the first pass flagged frontend-side)
- `api/app.py:663` · `stem[:120]` · wiki-upload title-from-filename truncation · **BACKEND** (small)
- `api/auth.py:145` · `secrets.token_hex(8)` · user-id entropy · **AMBIGUOUS** (id length)
- `api/auth.py:166` · `secrets.token_urlsafe(32)` · session-token entropy · **BACKEND** (security — propose-first)
- `api/auth.py:178` · `samesite = "lax"` · session-cookie SameSite (CSRF posture) · **BACKEND** (propose-first)
- `core/intake/rate_limiter.py:84` · `now - self._last_prune < 1.0` · min interval between O(keys) prune sweeps of the rate-limit map (DoS-behavior under session-id-flood) · **BACKEND**
- `api/run_driver.py:216-217` · `_MAX_SESSION_FILES = 30`, `_MAX_SESSION_FILE_BYTES = 64 * 1024 * 1024` · bounds on re-seeding a session's uploaded files into the workspace · **BACKEND** (resource/DoS)
- `core/artifacts.py:18` · `_MAX_NAME = 200` · max artifact filename length after flatten (client controls `name`) · **BACKEND** (fs-safety) *(name cap 200 was listed in api.yaml row of first pass — confirm dedupe; the classification as a client-controlled fs cap is the new note)*
- `core/orchestrator/mission_operate.py:77` · `DEFAULT_AUTONOMOUS_SAFE = frozenset({PermissionLevel.READ})` · permission ceiling an autonomous mission may act on before escalating to AWAITING_APPROVAL; **the code itself flags this belongs in config/** · **BACKEND** (authorization policy — propose-first, highest-value)

### → `config/backend/resilience.yaml`  *(PROPOSED new role file — these don't fit orchestrator/memory/security)*
- `foundation/vocab/constants.py:222` · `MAX_CONCURRENT_REQUESTS = 10` · pipeline-level concurrency semaphore · **BACKEND**
- `foundation/vocab/constants.py:223` · `MAX_CONCURRENT_LLM_CALLS = 5` · across all LLM roles combined · **BACKEND**
- `foundation/vocab/constants.py:224` · `MAX_QUEUE_DEPTH = 50` · requests waiting for a pipeline slot before fast-reject · **BACKEND**
- `foundation/vocab/constants.py:211,213` · `CB_FAILURE_THRESHOLD 5` / `CB_SUCCESS_THRESHOLD 2` · circuit-breaker trip/recover counts (listed above under security; natural home is here alongside the already-noted `CB_RECOVERY_TIMEOUT_S`) · **BACKEND**
- `foundation/vocab/constants.py:233` · `DEAD_LETTER_DIR = "workspace/dead_letters"` · where blocked/errored envelopes are written · **AMBIGUOUS** (ops path)
- `foundation/vocab/constants.py:234` · `DEAD_LETTER_MAX_ENTRIES = 10_000` · rotate after this many files · **BACKEND** (disk)
- `foundation/vocab/constants.py:235` · `DEAD_LETTER_RETENTION_DAYS = 30` · dead-letter retention window · **BACKEND** (disk/privacy)
- `foundation/vocab/constants.py:245` · `MAX_REASON_LENGTH = 500` · chars in `Envelope.reason` (tunable char cap; not a Flow *shape*) · **BACKEND** (note)
- `foundation/vocab/constants.py:246` · `MAX_ERROR_LENGTH = 2000` · chars in `Envelope.error` · **BACKEND** (note)
  *(excluded as genuine internals: `TRACE_ID_LENGTH 32`, `SPAN_ID_LENGTH 8` — id encoding, not dials)*

### → `config/backend/intake.yaml` (or fold into limits.yaml / security.yaml)
- `foundation/vocab/constants.py:55` · `MAX_INPUT_SIZE_BYTES = 50 * 1024 * 1024` · 50 MB hard cap on raw input (matches the frontend `uploads.ts` 50 MB per-file mirror — see below) · **BACKEND**
- `foundation/vocab/constants.py:83` · `MAX_TEXT_INPUT_CHARS = 100_000` · character cap on text content (VERIFIER_EXCERPT_CHARS references it; the cap itself was never listed) · **BACKEND**
- `foundation/vocab/constants.py:84` · `MAX_PDF_PAGES = 500` · pages before a PDF is rejected · **BACKEND**
- `foundation/vocab/constants.py:85` · `MAX_IMAGE_DIMENSION_PX = 8192` · width/height cap in pixels · **BACKEND**
- `foundation/vocab/constants.py:86` · `MAX_AUDIO_DURATION_S = 600` · 10-minute max audio · **BACKEND**
- `foundation/vocab/constants.py:87` · `MAX_VIDEO_DURATION_S = 300` · 5-minute max video · **BACKEND**
- `foundation/vocab/constants.py:60-68` · `TEXTUAL_MIME_TYPES` frozenset · which `application/*` MIME types intake treats as TEXT · **BACKEND** (admission policy — note)

### → `config/backend/api.yaml` (ops / display truncations / metering)
- `api/app.py:689` · `window = 30` · usage-metering trailing window in days (billing/margin surface) · **BACKEND**
- `api/run_state.py:21` · `_REPORT_CHUNK_WORDS = 6` · SSE report-streaming chunk size (words per delta) · **AMBIGUOUS** (perceived-streaming UX)
- `api/run_state.py:61` · `tool_calls[:12]` · process-summary tool-call display cap · **COSMETIC**
- `api/run_state.py:164,182,191` · `[:60]` expert name / `[:40]` domain / `[:400]` summary · expert-panel field truncations · **COSMETIC**
- `api/run_driver.py:157-159` · `_clip(..., 160)` / `_clip(..., 220)` · per-turn user/assistant recap truncation · **AMBIGUOUS** (context-budget)
- `api/run_driver.py:396` · `str(ctx.failure_error)[:300]` · failure-error truncation on the decision log · **COSMETIC**
- `api/hardening.py:110` · `errors[:3]` · number of validation errors surfaced in a 422 · **AMBIGUOUS** (info exposure)
- `api/app.py:502` · `Cache-Control: no-cache`, `X-Accel-Buffering: no` · SSE stream response headers (wrong value breaks live streaming behind a proxy) · **AMBIGUOUS**
- `api/app.py:599` · `first_line[:80]` · hydration-preview title truncation · **COSMETIC**
- `observability.py:74` · `maxBytes=10 * 1024 * 1024, backupCount=5` · log-rotation size + retained backups · **AMBIGUOUS** (ops/disk)
- `observability.py:31-36,46` · `_QUIET_LOGGERS` tuple + `WARNING` cap; root `level = logging.INFO` default · log verbosity defaults · **AMBIGUOUS** (ops)
- `core/artifacts.py:17,23` · `_BASE_ENV = "VRAKSHA_ARTIFACTS_DIR"` + default `api/data/artifacts` · artifact storage location · **AMBIGUOUS** (deployment path)
- `core/pipeline.py:122` · `user_id = "local-user"` default · default identity when a caller supplies none (harmless on web path — always overridden; load-bearing for CLI single-user scoping) · **AMBIGUOUS**
- `main.py:213` · `VRAKSHA_USER_ID` default `"local-user"` · CLI default identity (shared identity if unset) · **AMBIGUOUS**
- `delivery/delivery.py:35` · `VRAKSHA_CLI_QUIET != "1"` · flag suppressing the raw CLI decision-log/answer dump · **AMBIGUOUS** (feature flag)

### → `config/backend/copy.yaml` (user-facing strings — per D4)
- `core/pipeline.py:74-83` · stage `label`/`status` strings ("taking it in", "scanning input", "normalizing", "verifying", "working", "checking the answer", "delivering"; statuses sanitizing/verifying/orchestrating/filtering) — the CLI activity-feed + API run-status the user sees · **COSMETIC**
- `api/app.py:155` · "Too many attempts — wait a minute and try again." · 429 rate-limit copy (hardcodes "a minute", decoupled from `AUTH_RATE_WINDOW_S`) · **COSMETIC / drift-flag**
- `api/app.py:355` · "Say a little more to get started." · brief-too-short copy · **COSMETIC**
- `api/app.py:424` · "Say a little more to continue." · follow-up-too-short copy · **COSMETIC**
- `api/app.py:203` · `/login?error=oauth_unavailable` · OAuth-unavailable redirect target/copy · **COSMETIC**
- `api/app.py:760,765` · Stripe "not wired yet" 501 messages · billing placeholder copy · **COSMETIC**
- `api/hardening.py:99,114` · "An unexpected error occurred." / "Invalid request." · generic 500/422 bodies · **COSMETIC**
- `security/sanitizers/uploads.py:67-79` · upload-rejection copy (empty / "larger than the N MB limit" / unsupported type / "could not be security-scanned" / "rejected by the security scan") · **COSMETIC**
- `registry/capabilities/handler/tools.py:144` · "[redacted: external content failed sanitization]" · sanitization-failure placeholder · **COSMETIC**
- `tools/chart.py:266-281` · "No data to display." / "Chart generation failed." · empty/error SVG copy · **COSMETIC**
- `core/memory/writer.py:71-87,129-133` · distillation + supersession prompt copy (model-facing behavior copy; contains two typos — "Donot", "delievered") · **COSMETIC / flag**
- `core/orchestrator/utils/prompt.py:47-93` · orchestrator user-message scaffolding (section headers, "ATTACHED FILES"/"REVISION FEEDBACK"/delegation instructions) · **AMBIGUOUS** (prompt-engineering copy)
- `core/orchestrator/utils/prompt.py:24-29` · `_age()` provenance labels (", today" / ", yesterday" / ", {n}d ago") · **COSMETIC**
- `core/llm/search.py:93-99` · grounded-search prompt copy · **AMBIGUOUS** (prompt copy)
- `main.py:48-57,116-149` · CLI banner, `/help`, `_KIND_GLYPH` map, activity-feed glyphs · **COSMETIC** (operator-facing)

### → `config/frontend/*.yaml`  (frontend agent wires the UI — do NOT edit frontend/; propose)
**timings.yaml (COSMETIC):** `components/providers.tsx:15-17` React-Query `staleTime 15_000` / `retry 1` / `refetchOnWindowFocus false` · `lib/api/hooks.ts:203` hydration-preview `staleTime 30_000` · `hooks.ts:201` `length >= 3` before preview fires · `hooks.ts:304` `MAX_RECONNECT_ATTEMPTS 5` · `config/app.config.ts:98` http client `timeoutMs 30_000` · `lib/use-auto-resize.ts:15` `maxPx 320` + `composer.tsx:118` `280` overrides · `ui/dialog.tsx:8` `CLOSE_MS 170` · `app/app/page.tsx:52` `GREETING_MAX_AGE 30min` · `hydration-panel.tsx:324` flash hold `at+450` · `brand/memory-field.tsx:67` ambient loop `duration 6` · `(auth)/forgot-password/page.tsx:29` fake submit `700ms`.
**display.yaml (COSMETIC):** `config/demo.config.ts:34` `DEMO_REPORT_PREVIEW_CHARS 1400` · `app/memory/page.tsx:51` `ENTRY_PREVIEW_PX 176` · `marketing/demo-conversation.tsx:56` `NUDGE_AFTER 2` · `lib/utils.ts:15-16` number-abbrev thresholds (M/k) · `hydration-panel.tsx:55,58` `>= 4` in-reach chip cap · `hydration-panel.tsx:88` relevance→lit-rings `0.8/0.55` · `model-picker.tsx:419,466` dropdown open-direction `220` / min-height `150` · scroll-region caps (`project-switcher.tsx:175` 60vh/26rem, `command-palette.tsx:201` 40dvh, `run-activity.tsx:234` 60vh, `model-picker.tsx:130` max-h-64) · `composer.tsx:32` textarea `rows 3` (+ per-use 1/2/5/7 overrides).
**theme.yaml (COSMETIC):** `config/theme.config.ts:21-128` — the ENTIRE light/dark color system as editable JS (paper/ink, primary moss, memory amber, borders, destructive/success/warning, the `log-*` decision-log spectrum, `stage-*`/`glass-*`/`glow` hero-atmosphere colors incl. embedded rgba opacities). Not in the first pass's globals.css/layout.tsx ranges. · z-index scale (no central token): `app/layout.tsx:77` z-100, `toast.tsx:66` z-90, `sidebar.tsx:305` z-60, `project-switcher.tsx:175` z-50, `model-picker.tsx:130` z-20 · `config/brand.config.ts:43-54` `BUILTIN_MARK_RINGS` geometry + `BUILTIN_MARK_CORE_R 1.8` logo-shape params.
**copy.yaml (COSMETIC):** `app/app/page.tsx:16-38` `ANYTIME_GREETINGS` (12) + `timeGreetings()` time-of-day arrays + hour cutoffs (5/8/12/17/21) · `config/demo.config.ts:15-31` `DEMO_BRIEFS` (3) · `:45-67` `WORKSPACE_EXAMPLES` (3 composer suggestion cards) · placeholders (composer "Message Clannon…", "How can I help you today?", memory search/hints, command-palette, project-switcher seed hints, auth "you@studio.com"/"Your name") · empty-state/status copy (memory "Your wiki is empty"/"Nothing here yet", expert-panel "hasn't routed yet", hydration "4 tiers · empty", attachments "Up to N files per run.", hooks "Couldn't reconnect… Refresh to catch up.", demo "A canned run — no signup…").
**defaults.yaml (COSMETIC):** `config/nav.config.ts:15-33` `MARKETING_NAV` + `APP_NAV` order/icons · `config/brand.config.ts:26-35` brand `icon "builtin"` / `wordmark null` / `alt "Clannon"`.
**⚠ BACKEND-MIRROR (client caps the backend MUST also enforce — these are the important frontend finds):** `lib/uploads.ts:7` `MAX_FILES 10` (self-documented "MIRROR the backend"), `:8` `MAX_FILE_BYTES 50 MB` (mirrors backend `MAX_INPUT_SIZE_BYTES` above), `:10` `ACCEPTED_INPUT` extension allowlist · `config/app.config.ts:116` `briefMinChars 2` (already backend-authoritative via `/config`). *(`lib/api/mock.ts` has parallel caps but lives in the bundled mock simulator, not production — excluded.)*

### Long-tail externalization plan

**Recommended order — lowest-risk / behavior-preserving first, one area per commit** (each default == today's literal; suite green before every commit):

1. **`foundation/vocab/constants.py` D1 move — the whole file at once, behavior-preserving.** This is the largest, cleanest win: 35 product dials (28 net-new here + the ~7 D1 items the first pass already named) leave `foundation/` for the typed loader in one mechanical, greppable move. Low risk (values unchanged), high payoff (the "one place" goal, delivered). Split the landing YAMLs by section → `orchestrator.yaml` / `experts.yaml` / `tools.yaml` / `memory.yaml` / `intake.yaml` / **new** `resilience.yaml`. Do this FIRST — everything below references these homes.
2. **`experts.yaml` + `tools.yaml` code-level knobs** (artifact caps, recall/remember caps, video-frame interval, eager flags, model-role defaults) — pure resource/cost dials, no contract, no security surface. Safe.
3. **`memory.yaml` distillation/cost knobs** (`writer.py` token/finding/turn caps) — behavior-preserving, but land the two DEAD caps (`_MAX_TASK_CHARS`, `_MAX_ANSWER_CHARS`) as a LAW-1 decision first (wire or delete — don't externalize dead code). Fix the `max_hops=1` / `20` graph-layer duplication in the same commit (one source).
4. **`api.yaml` ops/display truncations + `copy.yaml`** — cosmetic caps and user-facing strings; low risk, but D4 (copy scope) is still owner-pending, so gate `copy.yaml` on that ruling.
5. **`config/frontend/*.yaml`** — cosmetics only; hand off to the frontend agent via a non-waking proposal (theme/timings/display/copy/defaults). The BACKEND-MIRROR caps (`uploads.ts`) are defined by the backend `limits.yaml`/`intake.yaml` and merely mirrored — the frontend reads them from `/config`.

**PROPOSE-FIRST (do NOT externalize silently — security / memory-scoping / margin / contract):**
- **Authorization:** `DEFAULT_AUTONOMOUS_SAFE` (autonomous-mission permission ceiling) — the single highest-value knob; changing it changes what a mission may do unattended.
- **Security scoring / policy:** `INJECTION_RULES` weights, `PII_REDACTED_ENTITIES`, `DANGEROUS_PDF_KEYS`, Presidio `language`, the filter `recipient` grounding string, severity-classification map, session-token entropy (`token_urlsafe(32)`), cookie `samesite`, password min-length (also fix the app.py↔auth.py duplication).
- **Memory scoping / infra:** Qdrant collection names + `Distance.COSINE` (a changed name or metric silently mixes or invalidates tenant data).
- **Margin/billing:** the `window=30` usage-metering window.
- **Resilience contract:** backpressure / circuit-breaker / dead-letter values sit under the same stability-first bar as the batch/graph work — propose the `resilience.yaml` shape before moving them.

**Count:** **~140 net-new tunables** (counting rule as stated at the top — ~115 backend `file:line` bullets across orchestrator/experts/tools/memory/security/resilience/intake/api/copy; ~21 frontend groups across timings/display/theme/copy/defaults + the BACKEND-MIRROR upload caps). `CB_FAILURE_THRESHOLD`/`CB_SUCCESS_THRESHOLD` appear under both security.yaml and resilience.yaml for placement discussion but are counted ONCE; `core/artifacts.py` name cap 200 + dir were in the first pass and are kept-with-a-note, not counted as net-new. This is on top of the ~90 the first pass inventoried. Notable LAW flags surfaced along the way (independent of the config question): the password-min duplication (`app.py:163`↔`auth.py:139`), two DEAD caps in `writer.py`, the triple-duplicated `max_hops` graph default + the second hardcoded `20`, and the "asserted/inferred" magic strings duplicated across graph stores.
