"""
settings — the typed loader for the owner's central `config/` control panel.

Reads the YAML under the repo-root `config/` (the ruled Phase-3 home) into validated,
typed values, failing LOUD at import time on anything malformed or out of range — a bad
config value never silently becomes wrong runtime behavior (LAW 5, fail-closed). This
module holds NO values of its own; every number lives in `config/*.yaml` (one source of
truth, LAW 4). Everything it exposes is BACKEND-CONTROLLED: server-enforced, never
accepted from a client.

Migration note (CENTRAL_CONFIG Phase 3): this is the new typed loader that
`config/README.md` names. It is being populated ONE config area per commit,
behavior-preserving (each default equals today's hardcoded value). The first area is the
budget/margin knobs; plans/limits/model-catalog still load through the older `config/`
package until their areas migrate here and that package is retired (decision D6).
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from foundation import PermissionLevel

# Repo-root config/ — this file is backend/settings.py, so config/ is one level up.
_CONFIG_ROOT = Path(__file__).resolve().parent.parent / "config"


def _load_mapping(relpath: str) -> dict:
    """Read one config YAML into a mapping, failing loud if it is missing or malformed —
    a broken control panel must stop startup, never degrade to a guessed default."""
    path = _CONFIG_ROOT / relpath
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"config: required file missing: {path}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"config: {path} did not parse to a mapping (got {type(data).__name__})")
    return data


class BudgetConfig(BaseModel):
    """The spend/margin ceiling + context-history budget knobs (`config/backend/budget.yaml`).

    `spend_ceiling_fraction` is the SINGLE source of the margin invariant (ADR-0004 / the
    Redis atomic budget): a user may spend at most this fraction of what they paid on real
    cost, and the remainder is our guaranteed minimum margin. Read the ceiling ONLY from
    here (`settings.SPEND_CEILING_FRACTION`) — no call site may hardcode or re-derive it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    spend_ceiling_fraction: float = Field(gt=0.0, le=1.0)  # 0 < f ≤ 1; ≥(1-f) is locked margin
    history_char_budget: int = Field(gt=0)                 # chars before oldest turns condense
    verbatim_turn_floor: int = Field(ge=1)                 # most-recent turns always kept whole
    infra_cost_per_call_micros: int = Field(ge=0)          # µ$ flat, every LLM call (B2b)
    infra_cost_per_second_micros: int = Field(ge=0)        # µ$ per wall-clock second (B2b)
    default_memory_budget_tokens: int = Field(gt=0)        # default hydration token budget
    memory_chars_per_token: int = Field(gt=0)              # chars/token fallback if tiktoken fails


def _load_budget() -> BudgetConfig:
    raw = _load_mapping("backend/budget.yaml")
    try:
        return BudgetConfig(**raw)
    except ValidationError as exc:
        # Fail loud with the exact field(s) at fault — never start on an invalid money knob.
        raise RuntimeError(f"config/backend/budget.yaml is invalid:\n{exc}") from exc


class ModelPrice(BaseModel):
    """One model's token cost, in micro-dollars per token (µ$/token)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_micros_per_token: float = Field(ge=0.0)
    output_micros_per_token: float = Field(ge=0.0)


class PricingConfig(BaseModel):
    """Per-model LLM pricing (`config/backend/pricing.yaml`), for the real-cost budget.

    FAIL-CLOSED: `price_for()` raises on a model with no entry — an un-priced model must
    BLOCK a spend, never be charged as free (which would silently blow the margin). Adding
    a model to the roster without a price here is a loud error, by design (decision B3).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    models: dict[str, ModelPrice]

    def price_for(self, model_id: str) -> ModelPrice:
        try:
            return self.models[model_id]
        except KeyError:
            raise KeyError(
                f"no price for model {model_id!r} in config/backend/pricing.yaml — "
                "add it (fail-closed: an un-priced model cannot be charged)"
            ) from None


def _load_pricing() -> PricingConfig:
    raw = _load_mapping("backend/pricing.yaml")
    try:
        return PricingConfig(**raw)
    except ValidationError as exc:
        raise RuntimeError(f"config/backend/pricing.yaml is invalid:\n{exc}") from exc


class TierTrust(BaseModel):
    """Per-tier ranking weight — WIKI (user-authored) outranks the machine-derived tiers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    wiki: float = Field(gt=0.0)
    semantic: float = Field(gt=0.0)
    episodic: float = Field(gt=0.0)
    procedural: float = Field(gt=0.0)


class TierFloor(BaseModel):
    """Per-tier minimum fraction of the hydration budget (water-filling floor)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    wiki: float = Field(ge=0.0, le=1.0)
    semantic: float = Field(ge=0.0, le=1.0)
    episodic: float = Field(ge=0.0, le=1.0)
    procedural: float = Field(ge=0.0, le=1.0)


class MemoryConfig(BaseModel):
    """The four-tier memory system's ranking/acceptance knobs (`config/backend/memory.yaml`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tier_trust: TierTrust
    tier_floor: TierFloor
    recency_half_life_s: float = Field(gt=0.0)
    recency_floor: float = Field(ge=0.0, le=1.0)
    min_accept_confidence: float = Field(ge=0.0, le=1.0)
    dedup_similarity: float = Field(ge=0.0, le=1.0)
    max_content_chars: int = Field(gt=0)
    supersession_floor: float = Field(ge=0.0, le=1.0)
    supersession_timeout_s: float = Field(gt=0.0)
    embed_retry_after_s: float = Field(gt=0.0)
    qdrant_request_timeout_s: float = Field(gt=0.0)
    graph_max_hops_ceiling: int = Field(ge=1)
    # D1 move — migrating out of foundation/vocab/constants.py (MEMORY_* group).
    read_timeout_s: float = Field(gt=0.0)
    write_timeout_s: float = Field(gt=0.0)
    search_top_k: int = Field(gt=0)
    relevance_floor: float = Field(ge=0.0, le=1.0)
    distill_max_retries: int = Field(ge=0)

    @model_validator(mode="after")
    def _dedup_is_a_subset_of_supersession(self) -> "MemoryConfig":
        # Dedup (a same-tier refresh) must be a STRICT SUBSET of the wider supersession
        # candidate band. If a config edit ever inverted these, the dedup path would start
        # swallowing what should be LLM-judged supersession candidates — fail loud, not silent.
        if self.dedup_similarity < self.supersession_floor:
            raise ValueError(
                f"dedup_similarity ({self.dedup_similarity}) must be >= supersession_floor "
                f"({self.supersession_floor}) — dedup is a strict subset of the supersession band"
            )
        return self


def _load_memory() -> MemoryConfig:
    raw = _load_mapping("backend/memory.yaml")
    try:
        return MemoryConfig(**raw)
    except ValidationError as exc:
        raise RuntimeError(f"config/backend/memory.yaml is invalid:\n{exc}") from exc


class OrchestratorConfig(BaseModel):
    """Orchestrator-tier tunables (`config/backend/orchestrator.yaml`): the routing
    advisory-scorer's default sharpness + entropy bands, the chat-vs-deliverable split
    threshold, the substantive-turn memory gate, and the degraded answer's bounds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    routing_default_temperature: float = Field(gt=0.0)
    routing_entropy_focused_below: float = Field(ge=0.0, le=1.0)
    routing_entropy_dispersed_at_or_above: float = Field(ge=0.0, le=1.0)
    chat_reply_max_chars: int = Field(gt=0)
    substantive_task_chars: int = Field(gt=0)
    substantive_answer_chars: int = Field(gt=0)
    episodic_task_excerpt_chars: int = Field(gt=0)
    episodic_answer_excerpt_chars: int = Field(gt=0)
    decision_record_content_chars: int = Field(gt=0)
    degraded_per_finding_chars: int = Field(gt=0)
    degraded_max_findings: int = Field(gt=0)
    degraded_confidence: float = Field(ge=0.0, le=1.0)
    # D1 move — migrating out of foundation/vocab/constants.py.
    timeout_s: float = Field(gt=0.0)
    max_tokens: int = Field(gt=0)
    max_turns: int = Field(gt=0)
    max_retries: int = Field(ge=0)
    turn_wall_clock_s: float = Field(gt=0.0)

    @model_validator(mode="after")
    def _entropy_bands_ordered(self) -> "OrchestratorConfig":
        if not (self.routing_entropy_focused_below < self.routing_entropy_dispersed_at_or_above):
            raise ValueError(
                "routing_entropy_focused_below must be < routing_entropy_dispersed_at_or_above"
            )
        return self


def _load_orchestrator() -> OrchestratorConfig:
    raw = _load_mapping("backend/orchestrator.yaml")
    try:
        return OrchestratorConfig(**raw)
    except ValidationError as exc:
        raise RuntimeError(f"config/backend/orchestrator.yaml is invalid:\n{exc}") from exc


class ExpertsConfig(BaseModel):
    """Expert-tier tunables (`config/backend/experts.yaml`): media-preprocessing bounds,
    the media expert's inline-attachment size limit, and the expert-handler's
    artifact-capture + need-context caps."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_doc_chars: int = Field(gt=0)
    min_pdf_text_chars: int = Field(ge=0)
    pdf_render_dpi: int = Field(gt=0)
    max_pdf_render_pages: int = Field(gt=0)
    max_transcript_chars: int = Field(gt=0)
    video_frame_every_s: int = Field(gt=0)
    max_video_frames: int = Field(gt=0)
    ffmpeg_timeout_s: float = Field(gt=0.0)
    media_inline_limit_bytes: int = Field(gt=0)
    max_artifacts: int = Field(gt=0)
    max_artifact_bytes: int = Field(gt=0)
    need_context_max_items: int = Field(gt=0)
    # D1 move — migrating out of foundation/vocab/constants.py.
    timeout_s: float = Field(gt=0.0)
    max_concurrent: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    max_turns: int = Field(gt=0)


def _load_experts() -> ExpertsConfig:
    raw = _load_mapping("backend/experts.yaml")
    try:
        return ExpertsConfig(**raw)
    except ValidationError as exc:
        raise RuntimeError(f"config/backend/experts.yaml is invalid:\n{exc}") from exc


class ToolsConfig(BaseModel):
    """Tool-tier tunables (`config/backend/tools.yaml`): per-tool caps (diff, fetch_url,
    http_request, memory_search), chart SVG geometry, and the remember/recall bounds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    diff_max_chars: int = Field(gt=0)
    fetch_url_max_redirects: int = Field(ge=0)
    http_request_max_headers: int = Field(gt=0)
    memory_search_default_results: int = Field(gt=0)
    memory_search_max_results: int = Field(gt=0)
    chart_width: int = Field(gt=0)
    chart_height: int = Field(gt=0)
    chart_margin_top: int = Field(ge=0)
    chart_margin_right: int = Field(ge=0)
    chart_margin_bottom: int = Field(ge=0)
    chart_margin_left: int = Field(ge=0)
    chart_max_bar_width: float = Field(gt=0.0)
    remember_max_chars: int = Field(gt=0)
    recall_max_hits: int = Field(gt=0)
    remember_write_confidence: float = Field(ge=0.0, le=1.0)
    tool_output_preview_chars: int = Field(gt=0)
    # D1 move — migrating out of foundation/vocab/constants.py.
    timeout_s: float = Field(gt=0.0)
    sandbox_timeout_s: float = Field(gt=0.0)
    max_retries: int = Field(ge=0)
    max_output_bytes: int = Field(gt=0)
    fetch_max_response_bytes: int = Field(gt=0)

    @model_validator(mode="after")
    def _search_bounds_ordered(self) -> "ToolsConfig":
        if not (self.memory_search_default_results <= self.memory_search_max_results):
            raise ValueError("memory_search_default_results must be <= memory_search_max_results")
        return self


def _load_tools() -> ToolsConfig:
    raw = _load_mapping("backend/tools.yaml")
    try:
        return ToolsConfig(**raw)
    except ValidationError as exc:
        raise RuntimeError(f"config/backend/tools.yaml is invalid:\n{exc}") from exc


class LlmConfig(BaseModel):
    """LLM retry/backoff bounds (`config/backend/llm.yaml`) — the `core/llm/retry.py` choke point."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    transient_max_retries: int = Field(ge=0)
    fallback_max_retries: int = Field(ge=0)
    retry_base_delay_s: float = Field(gt=0.0)
    retry_max_delay_s: float = Field(gt=0.0)


def _load_llm() -> LlmConfig:
    raw = _load_mapping("backend/llm.yaml")
    try:
        return LlmConfig(**raw)
    except ValidationError as exc:
        raise RuntimeError(f"config/backend/llm.yaml is invalid:\n{exc}") from exc


# The HARD ceiling on autonomous-action permissions (D7) — a Python constant, NEVER
# YAML-overridable. This is the actual "floor" the owner required: no config edit, however
# malformed or hostile, can let an autonomous mission act above this set without human
# approval. EXECUTE/NETWORK/ELEVATED are categorically excluded (running code, outbound
# calls, elevated grants are never autonomous). Widening it is a deliberate code change
# with owner sign-off (docket D7, option B).
_AUTONOMOUS_SAFE_CEILING: frozenset[PermissionLevel] = frozenset({PermissionLevel.READ})

# Hard ceilings on the sandbox resource caps (D8) — Python constants, NEVER YAML-overridable,
# set to today's values. Config may only TIGHTEN a sandbox (LOWER these); a config edit that
# RAISES any past its ceiling fails loud at load — no config can grant a sandboxed job more
# memory/cpu/pids/tmpfs, a longer run, or a bigger output flood than is safe. They are NUMBERS,
# not docker unit-strings, deliberately: a string ceiling ("1024m" <= "512m") is fail-OPEN.
# (The sandbox's isolation STRUCTURE — network none / read-only / non-root / mounts / the
# _ENABLE gate / the image — stays in code, never config-toggleable; not represented here.)
_SANDBOX_CEILINGS: dict[str, float] = {
    "sandbox_memory_mb": 512,
    "sandbox_cpus": 1.0,
    "sandbox_pids": 256,
    "sandbox_tmpfs_mb": 64,
    "sandbox_run_timeout_s": 60.0,
    "sandbox_max_output_chars": 20000,
}

# D8 PII floor — config's Presidio entity allow-list may only ADD to this baseline, never drop
# an entity (dropping one silently stops redacting a real PII category). Python constant, not YAML.
_PII_BASELINE_ENTITIES: frozenset[str] = frozenset({
    "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "IBAN_CODE", "US_BANK_NUMBER",
    "US_SSN", "US_ITIN", "US_PASSPORT", "US_DRIVER_LICENSE", "UK_NHS",
    "MEDICAL_LICENSE", "CRYPTO", "IP_ADDRESS",
})

# D8 filter-grounding bounds — config may WIDEN the filter's grounding window (accuracy) but never
# NARROW below today (over-blocks legit reports — the documented regression) nor exceed the ceiling
# (per-turn filter token-cost / DoS guard). Ceiling = 4× the floor. Python constants, not YAML.
_FILTER_GROUNDING_FLOORS: dict[str, int] = {
    "filter_grounding_max_findings": 8,
    "filter_grounding_max_finding_chars": 1500,
    "filter_grounding_max_tool_calls": 12,
    "filter_grounding_max_tool_result_chars": 1200,
}
_FILTER_GROUNDING_CEILINGS: dict[str, int] = {k: v * 4 for k, v in _FILTER_GROUNDING_FLOORS.items()}


class SecurityConfig(BaseModel):
    """Security-authorization policy (`config/backend/security.yaml`). BACKEND-CONTROLLED and
    HARD-FLOORED: config may only TIGHTEN a value, never loosen it below the ceiling enforced
    here — a config edit that tries to exceed the ceiling fails loud at startup."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    autonomous_safe_permissions: frozenset[PermissionLevel]
    # Sandbox resource caps — the six below are ceiling-bounded (config may only lower them).
    sandbox_memory_mb: int = Field(gt=0)
    sandbox_cpus: float = Field(gt=0.0)
    sandbox_pids: int = Field(gt=0)
    sandbox_tmpfs_mb: int = Field(gt=0)
    sandbox_run_timeout_s: float = Field(gt=0.0)
    sandbox_max_output_chars: int = Field(gt=0)
    # Ops waits on the docker CLI (not the workload) — no security direction, no ceiling.
    sandbox_create_timeout_s: float = Field(gt=0.0)
    sandbox_teardown_timeout_s: float = Field(gt=0.0)
    # Sanitizer + filter-retry — plain D1, no floor/ceiling.
    sanitizer_timeout_total_s: float = Field(gt=0.0)
    sanitizer_timeout_worker_s: float = Field(gt=0.0)
    sanitizer_max_workers: int = Field(gt=0)
    filter_max_retries: int = Field(ge=0)
    # PII redaction allow-list — floored (add-only).
    pii_redacted_entities: list[str]
    # Filter grounding window — floored + ceilinged.
    filter_grounding_max_findings: int = Field(gt=0)
    filter_grounding_max_finding_chars: int = Field(gt=0)
    filter_grounding_max_tool_calls: int = Field(gt=0)
    filter_grounding_max_tool_result_chars: int = Field(gt=0)

    @model_validator(mode="after")
    def _pii_entities_meet_floor(self) -> "SecurityConfig":
        missing = _PII_BASELINE_ENTITIES - set(self.pii_redacted_entities)
        if missing:
            raise ValueError(
                f"pii_redacted_entities is missing baseline entities {sorted(missing)} (docket D8) "
                "— config may only ADD to the redaction set, never drop below the safe baseline"
            )
        return self

    @model_validator(mode="after")
    def _filter_grounding_within_bounds(self) -> "SecurityConfig":
        for field, floor in _FILTER_GROUNDING_FLOORS.items():
            val, ceiling = getattr(self, field), _FILTER_GROUNDING_CEILINGS[field]
            if val < floor:
                raise ValueError(
                    f"{field}={val} is below the hard floor {floor} (docket D8) — config may only "
                    "WIDEN the filter's grounding window, never narrow it below the baseline"
                )
            if val > ceiling:
                raise ValueError(
                    f"{field}={val} exceeds the hard ceiling {ceiling} (docket D8, 4× floor) — a "
                    "config edit can't blow up per-turn filter token cost unboundedly"
                )
        return self

    @model_validator(mode="after")
    def _autonomous_within_ceiling(self) -> "SecurityConfig":
        if not self.autonomous_safe_permissions <= _AUTONOMOUS_SAFE_CEILING:
            raise ValueError(
                f"autonomous_safe_permissions "
                f"{sorted(p.value for p in self.autonomous_safe_permissions)} exceeds the hard "
                f"ceiling {sorted(p.value for p in _AUTONOMOUS_SAFE_CEILING)} (docket D7) — an "
                "autonomous mission may never act beyond this without human approval"
            )
        return self

    @model_validator(mode="after")
    def _sandbox_caps_within_ceilings(self) -> "SecurityConfig":
        for field, ceiling in _SANDBOX_CEILINGS.items():
            if getattr(self, field) > ceiling:
                raise ValueError(
                    f"{field}={getattr(self, field)} exceeds the hard sandbox ceiling {ceiling} "
                    "(docket D8) — config may only TIGHTEN the sandbox, never grant it more"
                )
        return self


def _load_security() -> SecurityConfig:
    raw = _load_mapping("backend/security.yaml")
    try:
        return SecurityConfig(**raw)
    except ValidationError as exc:
        raise RuntimeError(f"config/backend/security.yaml is invalid:\n{exc}") from exc


BUDGET: BudgetConfig = _load_budget()
PRICING: PricingConfig = _load_pricing()
MEMORY: MemoryConfig = _load_memory()
ORCHESTRATOR: OrchestratorConfig = _load_orchestrator()
EXPERTS: ExpertsConfig = _load_experts()
TOOLS: ToolsConfig = _load_tools()
LLM: LlmConfig = _load_llm()
SECURITY: SecurityConfig = _load_security()

# The margin invariant's ONE source of truth (ADR-0004). Every ceiling check reads THIS —
# nothing else defines or hardcodes the fraction. Regression-locked in tests/config_budget.py.
SPEND_CEILING_FRACTION: float = BUDGET.spend_ceiling_fraction

__all__ = [
    "BUDGET", "BudgetConfig", "SPEND_CEILING_FRACTION",
    "PRICING", "PricingConfig", "ModelPrice",
    "MEMORY", "MemoryConfig", "TierTrust", "TierFloor",
    "ORCHESTRATOR", "OrchestratorConfig",
    "EXPERTS", "ExpertsConfig",
    "TOOLS", "ToolsConfig",
    "LLM", "LlmConfig",
    "SECURITY", "SecurityConfig",
]
