# Central `config/` — Phase 1 Discovery: Inventory + Proposed Layout

**Status: DISCOVERY COMPLETE — awaiting owner approval before ANY externalization (Phase 3).**
Nothing has been moved yet. This is the map + the decisions, per the CENTRAL_CONFIG spec.

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
