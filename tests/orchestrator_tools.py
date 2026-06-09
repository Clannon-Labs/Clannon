"""Tests for the generic registry-driven ToolHandler + the real tools."""

import asyncio

from pydantic import BaseModel

from foundation import PermissionLevel, VrakshaContext, constants
from registry.capabilities import CapabilityKind, CapabilityRegistry, ToolSpec, discover
from registry.capabilities import validate
from registry.capabilities import ToolRequest
from registry.capabilities.handler import ToolHandler
import registry.capabilities.handler.tools as handler_mod


class EchoIn(BaseModel):
    text: str


class EchoOut(BaseModel):
    text: str


def _ctx():
    return VrakshaContext.new("s")


def _reg(impl, *, name="echo", domain="t", permission=PermissionLevel.READ):
    reg = CapabilityRegistry()
    spec = ToolSpec(
        name=name, kind=CapabilityKind.TOOL, description="d", domain=domain, impl=impl,
        input_schema=EchoIn, output_schema=EchoOut, permission=permission,
    )
    reg.register(spec, validate(spec))
    return reg


def test_success_records_call():
    class Echo:
        async def run(self, args):
            return EchoOut(text=args.text.upper())
    ctx = _ctx()
    rec = asyncio.run(ToolHandler(registry=_reg(Echo)).call_tool(
        ToolRequest(key="t.echo", arguments={"text": "hi"}), ctx))
    assert rec.success and rec.result["text"] == "HI"
    assert len(ctx.tool_calls) == 1


def test_unknown_tool_never_silent():
    rec = asyncio.run(ToolHandler(registry=CapabilityRegistry()).call_tool(
        ToolRequest(key="x.y", arguments={}), _ctx()))
    assert rec.success is False and "unknown" in rec.error


def test_permission_denied():
    class Net:
        async def run(self, args):
            return EchoOut(text="x")
    handler = ToolHandler(registry=_reg(Net, permission=PermissionLevel.NETWORK),
                          grants=frozenset({PermissionLevel.READ}))
    rec = asyncio.run(handler.call_tool(ToolRequest(key="t.echo", arguments={"text": "x"}), _ctx()))
    assert rec.success is False and "permission" in rec.error


def test_bad_arguments():
    class Echo:
        async def run(self, args):
            return EchoOut(text=args.text)
    rec = asyncio.run(ToolHandler(registry=_reg(Echo)).call_tool(
        ToolRequest(key="t.echo", arguments={"wrong": "x"}), _ctx()))
    assert rec.success is False and "arguments" in rec.error


def test_timeout_never_silent(monkeypatch):
    monkeypatch.setattr(constants, "TOOL_TIMEOUT_S", 0.01)

    class Slow:
        async def run(self, args):
            await asyncio.sleep(0.1)
            return EchoOut(text="late")
    rec = asyncio.run(ToolHandler(registry=_reg(Slow)).call_tool(
        ToolRequest(key="t.echo", arguments={"text": "x"}), _ctx()))
    assert rec.success is False and "timed out" in rec.error


def test_network_output_sanitized(monkeypatch):
    class Net:
        async def run(self, args):
            return EchoOut(text="secret blob")

    class _Scanned:
        passed = False
        sanitized_text = None

    async def fake_scan(text):
        return _Scanned()
    monkeypatch.setattr(handler_mod, "scan_text", fake_scan)

    rec = asyncio.run(ToolHandler(registry=_reg(Net, permission=PermissionLevel.NETWORK)).call_tool(
        ToolRequest(key="t.echo", arguments={"text": "x"}), _ctx()))
    assert rec.success and "redacted" in rec.result["text"]


def test_real_calculator():
    discover()
    ctx = _ctx()
    rec = asyncio.run(ToolHandler().call_tool(
        ToolRequest(key="math.calculator", arguments={"expression": "2+2"}), ctx))
    assert rec.result["result"] == 4.0


def test_python_exec_disabled_by_default(monkeypatch):
    discover()
    monkeypatch.delenv("VRAKSHA_ENABLE_PYTHON_EXEC", raising=False)
    rec = asyncio.run(ToolHandler().call_tool(
        ToolRequest(key="code.python_exec", arguments={"code": "print(1+1)"}), _ctx()))
    assert rec.success and rec.result["ok"] is False and "disabled" in rec.result["output"]


def test_python_exec_runs_when_opted_in(monkeypatch):
    discover()
    monkeypatch.setenv("VRAKSHA_ENABLE_PYTHON_EXEC", "1")
    rec = asyncio.run(ToolHandler().call_tool(
        ToolRequest(key="code.python_exec", arguments={"code": "print(1+1)"}), _ctx()))
    assert rec.success and rec.result["ok"] and rec.result["output"] == "2"


def test_fetch_url_blocks_internal_targets():
    discover()
    handler = ToolHandler()
    for url in ("http://127.0.0.1/", "http://localhost/", "http://169.254.169.254/latest/meta-data/"):
        rec = asyncio.run(handler.call_tool(ToolRequest(key="web.fetch_url", arguments={"url": url}), _ctx()))
        assert rec.success is False and ("block" in rec.error.lower() or "resolve" in rec.error.lower())


def test_fetch_url_rejects_non_http_scheme():
    discover()
    rec = asyncio.run(ToolHandler().call_tool(
        ToolRequest(key="web.fetch_url", arguments={"url": "file:///etc/passwd"}), _ctx()))
    assert rec.success is False and "http" in rec.error.lower()
