"""
foundation/vocab/constants.py

Every timeout, limit, size cap, retry count, and threshold lives here.
Nothing is hardcoded anywhere else in Vraksha.

Rule: if you find yourself writing a number or a magic string
directly in a module, it belongs here instead.

Sections:
    PIPELINE        — overall request lifecycle limits
    INTAKE          — request admission and raw input limits
    SANITIZERS      — parallel worker limits and file size caps
    VERIFIER        — input verification LLM limits
    ORCHESTRATOR    — main LLM reasoning loop limits
    TOOLS           — tool invocation limits
    EXPERTS         — expert invocation limits
    FILTER          — output filter LLM limits
    MEMORY          — qdrant and memory layer limits
    CIRCUIT BREAKER — failure thresholds and cooldown windows
    BACKPRESSURE    — concurrency and queue limits
    DEAD LETTER     — dead letter store limits
    TRANSPORT       — envelope and message limits
"""


# ---------------------------------------------------------------------------
# PIPELINE
# Overall request lifecycle. These are the outermost limits.
# ---------------------------------------------------------------------------

# The ENFORCED whole-turn wall clock — MIGRATED to config (D1, single-source):
# config/backend/orchestrator.yaml -> settings.ORCHESTRATOR.turn_wall_clock_s. One deadline is
# set at turn start (`ctx.turn_deadline`); the initial orchestrator pass AND every filter-revision
# budget their `wait_for` against the time REMAINING, so a turn can never exceed this — even
# across revisions. (Previously each of ≤FILTER_MAX_REVISIONS revisions got a FRESH
# ORCHESTRATOR timeout, compounding to ~1440s/24min with no outer kill.) Set above the
# orchestrator's own timeout so a single legitimate pass is never cut short; it is a hard
# ceiling on runaway. Budget exhausted ⇒ fail closed (no delivery). Tunable.
# Output-filter recovery budget — see FILTER_MAX_REVISIONS in the FILTER section.


# ---------------------------------------------------------------------------
# INTAKE
# Cheap admission checks before sanitizers, normalizers, or LLMs do work.
# The in-memory rate limiter is per process. Replace its backend with Redis
# when running multiple app containers that need shared request accounting.
# ---------------------------------------------------------------------------

# INTAKE knobs — MIGRATED to config (D1, single-source): config/backend/intake.yaml ->
# settings.INTAKE.* (rate-limiter window/max-requests/tracked-keys, the global burst window, and
# max_input_size_bytes — the 50 MiB raw-input cap). core/intake/{rate_limiter,intake}.py and
# security/sanitizers/uploads.py read them from there.

# Textual MIME types that intake accepts as Modality.TEXT in addition to the
# "text/*" family. libmagic reports structured text (JSON/XML/CSV/YAML) and
# empty input under "application/*", which are still plain text to an LLM.
TEXTUAL_MIME_TYPES = frozenset({
    "application/json",
    "application/xml",
    "application/x-ndjson",
    "application/csv",
    "application/yaml",
    "application/x-yaml",
    "application/x-empty",
})


# ---------------------------------------------------------------------------
# SANITIZERS — MIGRATED to config (D1, single-source): config/backend/security.yaml ->
# settings.SECURITY.{sanitizer_timeout_total_s, sanitizer_timeout_worker_s,
# sanitizer_max_workers, max_text_input_chars, max_pdf_pages, max_image_dimension_px,
# max_audio_duration_s, max_video_duration_s}. max_text_input_chars is repointed
# (core/normalizer/builders.py, core/verifier/constants.py — backend's own tree). The
# other four are placed but NOT YET repointed — security/sanitizers/workers/
# {image,pdf,audio,video}.py still read the constants below; that tree is the security
# specialist's, so the repoint is proposed to them (proposals/to-security/), not done
# here. Remove these four once that repoint lands.
# ---------------------------------------------------------------------------

MAX_PDF_PAGES               = 500                 # pages before we reject the pdf
MAX_IMAGE_DIMENSION_PX      = 8192                # width or height cap in pixels
MAX_AUDIO_DURATION_S        = 600                 # 10 minutes max audio
MAX_VIDEO_DURATION_S        = 300                 # 5 minutes max video


# ---------------------------------------------------------------------------
# VERIFIER
# Light LLM that classifies sanitized input before the orchestrator sees it.
# Should be fast class model, tight token limits.
# ---------------------------------------------------------------------------

# VERIFIER_* — MIGRATED to config (D1, single-source): config/backend/verifier.yaml ->
# settings.VERIFIER.{timeout_s, max_tokens, max_retries}. core/llm/registry.py + core/verifier/
# agent.py read them from there (owner control panel), not from a foundation constant.


# ---------------------------------------------------------------------------
# LLM TRANSIENT RETRY — MOVED to config/backend/llm.yaml → settings.LLM.* (D1 move,
# owner ruling D1(a)); core/llm/retry.py reads them from there now. Bounded exponential
# backoff around transient provider failures (429/5xx/drops) so a demand spike doesn't
# turn a legitimate request into a hard error; on exhaustion the error re-raises (fail-closed).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# ORCHESTRATOR
# Main LLM. Gets the most time — it does the real reasoning.
# ---------------------------------------------------------------------------

# ORCHESTRATOR_* (timeout_s, max_tokens, max_turns, max_retries) — MIGRATED to config (D1,
# single-source): config/backend/orchestrator.yaml -> settings.ORCHESTRATOR.*. Whole-loop wall
# time is sized to the workflow worst case: a parallel expert batch + the synthesis writer (one
# expert timeout each, they run in sequence) + decompose/answer turns + fallback retries.
# core/orchestrator/orchestrator.py + core/llm/registry.py read them from there now.


# ---------------------------------------------------------------------------
# TOOLS
# Per-tool invocation limits. The sandbox gets its own timeout.
# ---------------------------------------------------------------------------

# TOOL_* (timeout_s, sandbox_timeout_s, max_retries, max_output_bytes) + FETCH_MAX_RESPONSE_BYTES
# (the hard cap on a fetched HTTP body, enforced while streaming — a hostile/compromised server
# must never be able to stream us out of memory) — MIGRATED to config (D1, single-source):
# config/backend/tools.yaml -> settings.TOOLS.*. registry/capabilities + tools/ read them from
# there now.


# ---------------------------------------------------------------------------
# EXPERTS
# Experts can run longer than tools — they may themselves invoke tools.
# ---------------------------------------------------------------------------

# EXPERT_* (timeout_s, max_concurrent, max_output_tokens, max_turns) — MIGRATED to config (D1,
# single-source): config/backend/experts.yaml -> settings.EXPERTS.*. `max_turns` bounds the
# native tool loop inside one expert's run (it is itself a tool-driving agent), alongside the
# per-expert wall-clock timeout. registry/capabilities/handler/support.py reads them from there.


# ---------------------------------------------------------------------------
# FILTER
# Output filter LLM. Same class as verifier — fast, structured output only.
# ---------------------------------------------------------------------------

# FILTER_TIMEOUT_S / FILTER_MAX_TOKENS — DELETED (Law 1, dead code): declared here but
# never actually wired into any LLM call (core/llm/registry.py's model_settings_for_layer
# only special-cases "verifier" for a token+timeout cap — deliberately, per
# tests/model_settings.py::test_verifier_is_the_only_layer_with_a_token_and_timeout_cap
# — so "filter" was always on the generic uncapped path; these two constants had zero
# consumers anywhere in the tree, confirmed by search, found while auditing this file).
# FILTER_MAX_RETRIES / FILTER_MAX_REVISIONS — MIGRATED to config (D1): config/backend/
# security.yaml -> settings.SECURITY.{filter_max_retries, filter_max_revisions}.
# core.pipeline.recover_from_filter_block reads filter_max_revisions from there now.


# ---------------------------------------------------------------------------
# MEMORY
# ---------------------------------------------------------------------------
# The wired memory knobs (read/write timeout, search top-k, relevance floor, distill
# retries) MOVED to config/backend/memory.yaml → settings.MEMORY.* (the D1 config-depth
# move, owner ruling D1(a)); core/memory reads them from there now. Only these two
# PLANNED-but-unwired values remain here (no consumer yet — nothing to externalize).

MEMORY_MAX_ENTRY_CHARS      = 10_000 # PLANNED — not yet wired (manager caps at its own _MAX_CONTENT_CHARS)
MEMORY_WRITE_MAX_RETRIES    = 3      # PLANNED — not yet wired (record_write_proposals is not retry-bounded yet)


# ---------------------------------------------------------------------------
# CIRCUIT BREAKER
# Applied to: verifier LLM, filter LLM, orchestrator LLM, qdrant, sandboxes.
# FAILURE_THRESHOLD  — consecutive failures before tripping OPEN
# RECOVERY_TIMEOUT_S — seconds in OPEN state before moving to HALF_OPEN
# SUCCESS_THRESHOLD  — successes in HALF_OPEN before moving back to CLOSED
# ---------------------------------------------------------------------------

CB_FAILURE_THRESHOLD        = 5
CB_SUCCESS_THRESHOLD        = 2


# ---------------------------------------------------------------------------
# BACKPRESSURE
# Global concurrency limits. These are the last line of defense before
# the container runs out of resources.
# ---------------------------------------------------------------------------

MAX_CONCURRENT_REQUESTS     = 10     # pipeline-level semaphore
MAX_CONCURRENT_LLM_CALLS    = 5      # across all LLM roles combined
MAX_QUEUE_DEPTH             = 50     # requests waiting for a pipeline slot
                                     # beyond this, new requests are rejected fast


# ---------------------------------------------------------------------------
# DEAD LETTER
# Blocked or errored envelopes written here for inspection.
# ---------------------------------------------------------------------------

DEAD_LETTER_DIR             = "workspace/dead_letters"
DEAD_LETTER_MAX_ENTRIES     = 10_000  # rotate after this many files
DEAD_LETTER_RETENTION_DAYS  = 30


# ---------------------------------------------------------------------------
# TRANSPORT
# Envelope-level limits.
# ---------------------------------------------------------------------------

TRACE_ID_LENGTH             = 32     # hex chars (uuid4().hex)
SPAN_ID_LENGTH              = 8      # hex chars (truncated)
MAX_REASON_LENGTH           = 500    # chars in Envelope.reason
MAX_ERROR_LENGTH            = 2000   # chars in Envelope.error
