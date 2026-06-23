"""
Surface grounded-search source URLs to the delivered run shape.

Three scenarios mandated by the task spec:
  (a) A delivered run that ran a grounded search returns NON-EMPTY Run.sources
      from full_json() (the GET /runs/{id} payload), with each Source carrying
      id + title + url + domain.
  (b) Exactly one {type:"sources"} SSE frame is emitted during that run.
  (c) A run with NO grounded search returns an EMPTY sources list — never fabricated.

Hermetic: uses test-double ToolCallRecord / ExpertCallRecord carrying a 'sources'
list in their results; no network, no models, no paid keys.
"""

from foundation import ExpertCallRecord, ToolCallRecord, VrakshaContext
from api.run_state import RunState
import api.run_driver as rd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx_with_direct_search(urls: list[str]) -> VrakshaContext:
    """A ctx where the orchestrator called web_search directly and got sources."""
    ctx = VrakshaContext.new("s-direct", user_id="u1")
    ctx.tool_calls.append(ToolCallRecord(
        tool_name="search.web",
        arguments={"query": "UK skincare market"},
        result={"findings": "The market is growing.", "sources": urls},
        success=True,
        duration_ms=80.0,
    ))
    return ctx


def _ctx_with_expert_search(urls: list[str]) -> VrakshaContext:
    """A ctx where a research expert's sub-tool call to web_search produced sources."""
    ctx = VrakshaContext.new("s-expert", user_id="u1")
    sub_call = ToolCallRecord(
        tool_name="search.web",
        arguments={"query": "regulation cosmetics UK"},
        result={"findings": "UK Responsible Person required.", "sources": urls},
        success=True,
        duration_ms=65.0,
    )
    ctx.expert_calls.append(ExpertCallRecord(
        expert_name="research.web_researcher",
        arguments={"prompt": "research regulations"},
        result={"summary": "done", "full_content": "UK Responsible Person required."},
        success=True,
        sub_tool_calls=[sub_call],
    ))
    return ctx


def _ctx_no_search() -> VrakshaContext:
    """A ctx with tool calls that carry NO sources (non-web tools only)."""
    ctx = VrakshaContext.new("s-nosearch", user_id="u1")
    ctx.tool_calls.append(ToolCallRecord(
        tool_name="recall",
        arguments={"query": "prior work"},
        result={"text": "User prefers British English."},
        success=True,
        duration_ms=3.0,
    ))
    return ctx


def _run(rid: str = "r1") -> RunState:
    return RunState(id=rid, user_id="u1", title="t", brief="b", session_id=rid)


# ---------------------------------------------------------------------------
# _collect_sources unit tests
# ---------------------------------------------------------------------------

def test_collect_maps_urls_to_source_shape():
    urls = [
        "https://www.statista.com/outlook/cmo/skincare",
        "https://gov.uk/guidance/cosmetics",
    ]
    sources = rd._collect_sources(_ctx_with_direct_search(urls))
    assert len(sources) == 2
    first = sources[0]
    assert first["url"] == "https://www.statista.com/outlook/cmo/skincare"
    assert first["id"] == "src_1"
    assert first["title"]              # non-empty
    assert first["domain"] == "statista.com"   # www. stripped
    assert sources[1]["domain"] == "gov.uk"


def test_collect_strips_www_prefix_from_domain():
    sources = rd._collect_sources(_ctx_with_direct_search(["https://www.bbc.co.uk/news/tech"]))
    assert sources[0]["domain"] == "bbc.co.uk"


def test_collect_deduplicates_across_multiple_records():
    ctx = VrakshaContext.new("s-dedup", user_id="u1")
    shared_url = "https://example.com/shared"
    ctx.tool_calls.append(ToolCallRecord(
        tool_name="search.web",
        arguments={"query": "q1"},
        result={"findings": "f1", "sources": [shared_url, "https://example.com/only-first"]},
        success=True,
        duration_ms=50.0,
    ))
    ctx.tool_calls.append(ToolCallRecord(
        tool_name="search.web",
        arguments={"query": "q2"},
        result={"findings": "f2", "sources": [shared_url, "https://example.com/only-second"]},
        success=True,
        duration_ms=50.0,
    ))
    sources = rd._collect_sources(ctx)
    urls = [s["url"] for s in sources]
    assert urls == [shared_url, "https://example.com/only-first", "https://example.com/only-second"]
    # unique IDs assigned in order
    assert [s["id"] for s in sources] == ["src_1", "src_2", "src_3"]


def test_collect_spans_expert_sub_tool_calls():
    urls = ["https://mintel.com/report/uk-beauty"]
    sources = rd._collect_sources(_ctx_with_expert_search(urls))
    assert len(sources) == 1
    assert sources[0]["url"] == "https://mintel.com/report/uk-beauty"
    assert sources[0]["domain"] == "mintel.com"


def test_collect_skips_failed_tool_records():
    ctx = VrakshaContext.new("s-fail", user_id="u1")
    ctx.tool_calls.append(ToolCallRecord(
        tool_name="search.web",
        arguments={"query": "q"},
        result=None,
        success=False,
        error="timed out",
        duration_ms=75.0,
    ))
    assert rd._collect_sources(ctx) == []


def test_collect_ignores_tools_without_sources_field():
    ctx = VrakshaContext.new("s-no-field", user_id="u1")
    ctx.tool_calls.append(ToolCallRecord(
        tool_name="calculator.eval",
        arguments={"expr": "2+2"},
        result={"value": 4},
        success=True,
        duration_ms=1.0,
    ))
    assert rd._collect_sources(ctx) == []


# ---------------------------------------------------------------------------
# (a) non-empty Run.sources in full_json() — the GET /runs/{id} payload
# ---------------------------------------------------------------------------

def test_a_run_full_json_sources_populated_after_direct_search():
    run = _run("ra1")
    ctx = _ctx_with_direct_search([
        "https://www.statista.com/outlook/cmo/skincare",
        "https://gov.uk/guidance/cosmetics",
    ])
    run.sources = rd._collect_sources(ctx)
    j = run.full_json()

    assert len(j["sources"]) == 2
    for src in j["sources"]:
        assert src["id"] and src["title"] and src["url"] and src["domain"]


def test_a_run_full_json_sources_populated_from_expert_sub_calls():
    run = _run("ra2")
    ctx = _ctx_with_expert_search(["https://retail-week.com/beauty/dtc-2026"])
    run.sources = rd._collect_sources(ctx)
    j = run.full_json()

    assert len(j["sources"]) == 1
    assert j["sources"][0]["url"] == "https://retail-week.com/beauty/dtc-2026"
    assert j["sources"][0]["domain"] == "retail-week.com"


# ---------------------------------------------------------------------------
# (b) exactly one {type:"sources"} SSE frame emitted per delivered run
# ---------------------------------------------------------------------------

def test_b_exactly_one_sources_sse_frame_emitted():
    run = _run("rb1")
    srcs = rd._collect_sources(_ctx_with_direct_search(["https://example.com/a"]))
    run.sources = srcs
    run.emit({"type": "sources", "sources": srcs})

    sources_events = [e for e in run.events if e.get("type") == "sources"]
    assert len(sources_events) == 1
    assert sources_events[0]["sources"] == srcs
    assert sources_events[0]["sources"][0]["url"] == "https://example.com/a"


def test_b_sources_event_carries_correct_shape():
    run = _run("rb2")
    srcs = rd._collect_sources(_ctx_with_direct_search([
        "https://www.gov.uk/guidance/cosmetics",
    ]))
    run.sources = srcs
    run.emit({"type": "sources", "sources": srcs})

    evt = next(e for e in run.events if e.get("type") == "sources")
    assert evt["sources"][0]["domain"] == "gov.uk"
    assert evt["sources"][0]["id"].startswith("src_")


# ---------------------------------------------------------------------------
# (c) empty sources list when no grounded search was run — never fabricated
# ---------------------------------------------------------------------------

def test_c_collect_sources_empty_when_no_web_search():
    assert rd._collect_sources(_ctx_no_search()) == []


def test_c_run_full_json_sources_empty_by_default():
    run = _run("rc1")
    j = run.full_json()
    assert j["sources"] == []


def test_c_run_full_json_sources_empty_after_non_search_tools():
    run = _run("rc2")
    run.sources = rd._collect_sources(_ctx_no_search())
    j = run.full_json()
    assert j["sources"] == []
