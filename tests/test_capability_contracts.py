from src.capabilities import Actor, CapabilityRequest, CapabilityResult
from tools.mcp.adapter import McpAdapter
from tools.mcp.sdk import get_mcp_sdk_status


def test_capability_request_and_result_contracts_are_stable():
    request = CapabilityRequest(
        capability="file_read",
        arguments={"path": "README.md"},
        reason="inspect project overview",
        caller=Actor(kind="expert", name="planner"),
        budget_units=1,
        timeout_ms=1000,
    )

    result = CapabilityResult.ok(request, {"content": "hello"})

    assert request.to_dict()["caller"] == {"kind": "expert", "name": "planner"}
    assert result.to_dict()["request_id"] == request.request_id
    assert result.to_tool_output() == {
        "success": True,
        "data": {"content": "hello"},
        "error": None,
    }


def test_mcp_adapter_placeholder_fails_closed():
    request = CapabilityRequest(
        capability="external.docs_search",
        arguments={"query": "capability broker"},
        reason="test mcp placeholder",
        caller=Actor(kind="broker", name="test"),
    )

    result = McpAdapter().call(request)

    assert result.success is False
    assert result.error is not None
    assert result.error.code in {"mcp_not_configured", "mcp_sdk_missing"}


def test_mcp_sdk_boundary_imports_when_available():
    status = get_mcp_sdk_status()

    if status.available:
        assert status.version is not None
        assert status.client_session is not None
        assert status.stdio_server_parameters is not None
        assert status.stdio_client is not None
