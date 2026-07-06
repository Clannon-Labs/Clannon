"""Config loaders for the orchestrator / experts / tools areas (config-depth,
orchestration's proposed content). Locks the placed values (behavior-preserving —
each equals the constant the code used before) + the fail-loud validators. The
consumer swaps + their tests are orchestration's; this covers the config seam I own.
"""

import pytest
from pydantic import ValidationError

import settings
from settings import OrchestratorConfig, ExpertsConfig, ToolsConfig


# ── behavior-preserving value locks ────────────────────────────────────────────────────────

def test_orchestrator_values_match_todays_literals():
    o = settings.ORCHESTRATOR
    assert o.routing_default_temperature == 0.1
    assert (o.routing_entropy_focused_below, o.routing_entropy_dispersed_at_or_above) == (0.34, 0.67)
    assert o.chat_reply_max_chars == 600
    assert (o.substantive_task_chars, o.substantive_answer_chars) == (40, 200)
    assert (o.episodic_task_excerpt_chars, o.episodic_answer_excerpt_chars) == (200, 500)
    assert o.decision_record_content_chars == 500
    assert (o.degraded_per_finding_chars, o.degraded_max_findings, o.degraded_confidence) == (4000, 6, 0.1)


def test_experts_values_match_todays_literals():
    e = settings.EXPERTS
    assert (e.max_doc_chars, e.min_pdf_text_chars, e.pdf_render_dpi, e.max_pdf_render_pages) == (50000, 50, 150, 8)
    assert (e.max_transcript_chars, e.video_frame_every_s, e.max_video_frames, e.ffmpeg_timeout_s) == (50000, 5, 8, 90.0)
    assert e.media_inline_limit_bytes == 15728640
    assert (e.max_artifacts, e.max_artifact_bytes, e.need_context_max_items) == (20, 10485760, 5)


def test_d1_migrated_bounds_equal_the_foundation_constants():
    # ORCHESTRATOR_*/EXPERT_*/TOOL_* migrating out of foundation/vocab/constants.py (D1). Until
    # the consumers repoint + the constants are removed, config MUST equal the constant (no-op swap).
    import foundation.vocab.constants as c
    o, e, t = settings.ORCHESTRATOR, settings.EXPERTS, settings.TOOLS
    assert o.timeout_s == c.ORCHESTRATOR_TIMEOUT_S and o.max_tokens == c.ORCHESTRATOR_MAX_TOKENS
    assert o.max_turns == c.ORCHESTRATOR_MAX_TURNS and o.max_retries == c.ORCHESTRATOR_MAX_RETRIES
    assert o.turn_wall_clock_s == c.TURN_WALL_CLOCK_S
    assert e.timeout_s == c.EXPERT_TIMEOUT_S and e.max_concurrent == c.EXPERT_MAX_CONCURRENT
    assert e.max_output_tokens == c.EXPERT_MAX_OUTPUT_TOKENS and e.max_turns == c.EXPERT_MAX_TURNS
    assert t.timeout_s == c.TOOL_TIMEOUT_S and t.sandbox_timeout_s == c.TOOL_SANDBOX_TIMEOUT_S
    assert t.max_retries == c.TOOL_MAX_RETRIES and t.max_output_bytes == c.TOOL_MAX_OUTPUT_BYTES
    assert t.fetch_max_response_bytes == c.FETCH_MAX_RESPONSE_BYTES


def test_tools_values_match_todays_literals():
    t = settings.TOOLS
    assert (t.diff_max_chars, t.fetch_url_max_redirects, t.http_request_max_headers) == (200000, 5, 25)
    assert (t.memory_search_default_results, t.memory_search_max_results) == (8, 20)
    assert (t.chart_width, t.chart_height) == (560, 380)
    assert (t.chart_margin_top, t.chart_margin_right, t.chart_margin_bottom, t.chart_margin_left) == (50, 20, 80, 70)
    assert t.chart_max_bar_width == 80.0
    assert (t.remember_max_chars, t.recall_max_hits, t.remember_write_confidence) == (2000, 3, 0.95)
    assert t.tool_output_preview_chars == 1000


# ── fail-loud cross-field validators ────────────────────────────────────────────────────────

def _orch_kwargs(**over):
    base = dict(
        routing_default_temperature=0.1, routing_entropy_focused_below=0.34,
        routing_entropy_dispersed_at_or_above=0.67, chat_reply_max_chars=600,
        substantive_task_chars=40, substantive_answer_chars=200,
        episodic_task_excerpt_chars=200, episodic_answer_excerpt_chars=500,
        decision_record_content_chars=500, degraded_per_finding_chars=4000,
        degraded_max_findings=6, degraded_confidence=0.1,
        timeout_s=480.0, max_tokens=8096, max_turns=20, max_retries=2, turn_wall_clock_s=720.0,
    )
    return {**base, **over}


def test_orchestrator_entropy_bands_must_be_ordered():
    with pytest.raises(ValidationError):
        OrchestratorConfig(**_orch_kwargs(routing_entropy_focused_below=0.7,
                                          routing_entropy_dispersed_at_or_above=0.34))


def _tools_kwargs(**over):
    base = dict(
        diff_max_chars=200000, fetch_url_max_redirects=5, http_request_max_headers=25,
        memory_search_default_results=8, memory_search_max_results=20,
        chart_width=560, chart_height=380, chart_margin_top=50, chart_margin_right=20,
        chart_margin_bottom=80, chart_margin_left=70, chart_max_bar_width=80.0,
        remember_max_chars=2000, recall_max_hits=3, remember_write_confidence=0.95,
        tool_output_preview_chars=1000,
        timeout_s=30.0, sandbox_timeout_s=25.0, max_retries=2,
        max_output_bytes=1048576, fetch_max_response_bytes=5242880,
    )
    return {**base, **over}


def test_tools_search_default_must_not_exceed_max():
    with pytest.raises(ValidationError):
        ToolsConfig(**_tools_kwargs(memory_search_default_results=30, memory_search_max_results=20))


# ── extra-key + range rejection (one per area) ──────────────────────────────────────────────

def test_unknown_keys_rejected():
    with pytest.raises(ValidationError):
        OrchestratorConfig(**_orch_kwargs(bogus=1))
    with pytest.raises(ValidationError):
        ToolsConfig(**_tools_kwargs(bogus=1))


def test_out_of_range_rejected():
    with pytest.raises(ValidationError):
        ToolsConfig(**_tools_kwargs(remember_write_confidence=1.5))   # fraction > 1
    with pytest.raises(ValidationError):
        OrchestratorConfig(**_orch_kwargs(degraded_max_findings=0))   # must be > 0
