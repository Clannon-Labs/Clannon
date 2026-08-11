"""Delivery: the SSRF-guarded http.request tool + the notification expert that
POSTs a result to a webhook. The guard is the shared single-source one in tools._net."""

import asyncio

import pytest

from registry.capabilities import discover, registry
from tools._net import UnsafeUrlError, validate_public_url
from tools.http_request import HttpIn, HttpRequestTool


# ---- the shared SSRF guard (one source for every network tool) -------------


@pytest.mark.parametrize("bad", [
    "http://127.0.0.1/",                       # loopback
    "http://localhost/",                       # resolves to loopback
    "http://169.254.169.254/latest/meta-data/",# cloud metadata (link-local)
    "file:///etc/passwd",                      # non-http scheme
    "ftp://example.com/x",                     # non-http scheme
    "http://user:pass@example.com/",           # embedded credentials
])
def test_validate_public_url_rejects_unsafe(bad):
    with pytest.raises(UnsafeUrlError):
        asyncio.run(validate_public_url(bad))


# ---- the http.request tool is SSRF-gated before it ever connects -----------


def test_http_request_blocks_internal_target():
    tool = HttpRequestTool()
    with pytest.raises(UnsafeUrlError):
        asyncio.run(tool.run(HttpIn(url="http://169.254.169.254/", method="POST", json_body={"x": 1})))


def test_http_request_rejects_non_http_scheme():
    tool = HttpRequestTool()
    with pytest.raises(UnsafeUrlError):
        asyncio.run(tool.run(HttpIn(url="file:///etc/passwd")))


# ---- private-alpha policy: mutation capabilities stay absent ---------------


def test_private_alpha_denies_outbound_mutation_at_discovery_and_call():
    discover()
    from registry.capabilities import CapabilityKind, ToolRequest, ExpertRequest
    assert registry.get_tool("http.request") is None
    assert registry.get_expert("delivery.notifier") is None
    assert "http.request" not in {c["key"] for c in registry.cards(CapabilityKind.TOOL)}
    assert "delivery.notifier" not in {c["key"] for c in registry.cards(CapabilityKind.EXPERT)}

    from foundation import VrakshaContext
    from registry.capabilities.handler import ExpertHandler, ToolHandler

    ctx = VrakshaContext.new(session_id="s", user_id="u", trace_id="t")
    record = asyncio.run(
        ToolHandler(registry=registry).call_tool(
            ToolRequest(key="http.request", arguments={"url": "https://example.com"}), ctx
        )
    )
    assert not record.success and "unknown tool" in (record.error or "")
    summary = asyncio.run(
        ExpertHandler(registry=registry).run_experts(
            [ExpertRequest(key="delivery.notifier", arguments={"destination": "https://example.com", "content": "x"})], ctx
        )
    )[0]
    assert summary.finding_ref == ""
    assert "unknown expert" in summary.summary
