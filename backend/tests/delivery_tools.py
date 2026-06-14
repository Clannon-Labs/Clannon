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


# ---- the delivery expert + tool are registered, healthy, wired -------------


def test_delivery_notifier_and_http_tool_registered():
    discover()
    tool = registry.get_tool("http.request")
    from foundation import PermissionLevel
    assert tool is not None and tool.permission == PermissionLevel.NETWORK  # output gets re-sanitized

    exp = registry.get_expert("delivery.notifier")
    assert exp is not None and exp.model_role == "research"
    assert "http.request" in exp.tool_grants                                # its delivery channel

    assert {"delivery.notifier"} & {b.key for b in registry.broken()} == set()
    assert "http.request" not in {b.key for b in registry.broken()}
