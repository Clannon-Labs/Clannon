"""
constants.py

Every timeout, limit, size cap, retry count, and threshold lives here.
Nothing is hardcoded anywhere else in Vraksha.

Rule: if you find yourself writing a number or a magic string
directly in a module, it belongs here instead.

Sections:
    PIPELINE        — overall request lifecycle limits
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
# Overall request lifecycle. These are the outermost limits —
# if a full pipeline run exceeds PIPELINE_TIMEOUT_S, it is killed.
# ---------------------------------------------------------------------------

PIPELINE_TIMEOUT_S          = 120.0   # max wall time for one full user turn
MAX_OUTPUT_RETRIES          = 3       # times the filter can reject and re-send
                                      # to orchestrator before giving up


# ---------------------------------------------------------------------------
# SANITIZERS
# Parallel workers that inspect raw input.
# TOTAL timeout is the wall time for all workers combined (they run in parallel).
# PER_WORKER timeout is how long one modality worker can run before it is killed.
# ---------------------------------------------------------------------------

SANITIZER_TIMEOUT_TOTAL_S   = 15.0   # all workers combined must finish within this
SANITIZER_TIMEOUT_WORKER_S  = 10.0   # single worker timeout (text, pdf, image etc)
SANITIZER_MAX_WORKERS       = 10     # global semaphore — max concurrent workers
                                     # across all incoming requests

MAX_INPUT_SIZE_BYTES        = 50 * 1024 * 1024   # 50 MB hard cap on raw input
MAX_TEXT_INPUT_CHARS        = 100_000             # character cap on text content
MAX_PDF_PAGES               = 500                 # pages before we reject the pdf
MAX_IMAGE_DIMENSION_PX      = 8192                # width or height cap in pixels
MAX_AUDIO_DURATION_S        = 600                 # 10 minutes max audio
MAX_VIDEO_DURATION_S        = 300                 # 5 minutes max video


# ---------------------------------------------------------------------------
# VERIFIER
# Light LLM that classifies sanitized input before the orchestrator sees it.
# Should be fast class model, tight token limits.
# ---------------------------------------------------------------------------

VERIFIER_TIMEOUT_S          = 8.0    # if verifier takes longer, treat as ERROR
VERIFIER_MAX_TOKENS         = 512    # verifier only outputs structured JSON
VERIFIER_MAX_RETRIES        = 2      # retries on malformed output before ERROR


# ---------------------------------------------------------------------------
# ORCHESTRATOR
# Main LLM. Gets the most time — it does the real reasoning.
# ---------------------------------------------------------------------------

ORCHESTRATOR_TIMEOUT_S      = 90.0   # per reasoning turn, not total
ORCHESTRATOR_MAX_TOKENS     = 8096
ORCHESTRATOR_MAX_TURNS      = 20     # max back-and-forth turns in one session
                                     # before forcing a response


# ---------------------------------------------------------------------------
# TOOLS
# Per-tool invocation limits. The sandbox gets its own timeout.
# ---------------------------------------------------------------------------

TOOL_TIMEOUT_S              = 30.0   # per tool call wall time
TOOL_SANDBOX_TIMEOUT_S      = 25.0   # sandbox process must exit before tool timeout
TOOL_MAX_RETRIES            = 2      # retries on transient sandbox errors
TOOL_MAX_OUTPUT_BYTES       = 1 * 1024 * 1024   # 1 MB cap on tool output


# ---------------------------------------------------------------------------
# EXPERTS
# Experts can run longer than tools — they may themselves invoke tools.
# ---------------------------------------------------------------------------

EXPERT_TIMEOUT_S            = 120.0  # per expert invocation
EXPERT_MAX_CONCURRENT       = 3      # max experts running in parallel
                                     # for one orchestrator turn
EXPERT_MAX_OUTPUT_TOKENS    = 4096


# ---------------------------------------------------------------------------
# FILTER
# Output filter LLM. Same class as verifier — fast, structured output only.
# ---------------------------------------------------------------------------

FILTER_TIMEOUT_S            = 8.0
FILTER_MAX_TOKENS           = 512
FILTER_MAX_RETRIES          = 2      # retries on malformed output before ERROR


# ---------------------------------------------------------------------------
# MEMORY
# Qdrant read/write/retrieve limits.
# ---------------------------------------------------------------------------

MEMORY_READ_TIMEOUT_S       = 5.0
MEMORY_WRITE_TIMEOUT_S      = 10.0
MEMORY_SEARCH_TOP_K         = 10     # max results from semantic search
MEMORY_MAX_ENTRY_CHARS      = 10_000 # single memory entry size cap
MEMORY_WRITE_MAX_RETRIES    = 3      # retries on write failure before ERROR


# ---------------------------------------------------------------------------
# CIRCUIT BREAKER
# Applied to: verifier LLM, filter LLM, orchestrator LLM, qdrant, sandboxes.
# FAILURE_THRESHOLD  — consecutive failures before tripping OPEN
# RECOVERY_TIMEOUT_S — seconds in OPEN state before moving to HALF_OPEN
# SUCCESS_THRESHOLD  — successes in HALF_OPEN before moving back to CLOSED
# ---------------------------------------------------------------------------

CB_FAILURE_THRESHOLD        = 5
CB_RECOVERY_TIMEOUT_S       = 30.0
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
