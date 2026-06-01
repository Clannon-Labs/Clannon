from pathlib import Path

from get_root import root
from registry.discovery import discover_registry_modules
from src.capabilities import Actor, CapabilityBroker, CapabilityRequest


def _request(capability: str, arguments: dict, reason: str = "test broker path"):
    return CapabilityRequest(
        capability=capability,
        arguments=arguments,
        reason=reason,
        caller=Actor(kind="agent", name="test"),
        budget_units=5,
    )


def test_broker_routes_filesystem_capabilities_and_audits():
    broker = CapabilityBroker()
    test_path = Path(".capability_broker_test.txt")
    absolute_path = root.project / test_path

    try:
        write_result = broker.call(
            _request(
                "file_write",
                {"path": test_path.as_posix(), "content": "alpha\nbeta\n"},
            )
        )
        assert write_result.success is True

        read_result = broker.call(
            _request("file_read", {"path": test_path.as_posix()})
        )
        assert read_result.success is True
        assert read_result.data == {
            "path": test_path.as_posix(),
            "content": "alpha\nbeta\n",
            "bytes": 11,
            "truncated": False,
        }

        events = broker.audit_log.events()
        assert len(events) == 2
        assert events[-1].capability == "file_read"
        assert events[-1].allowed is True

    finally:
        if absolute_path.exists():
            absolute_path.unlink()


def test_broker_requires_request_reason():
    result = CapabilityBroker().call(
        _request("file_stat", {"path": "README.md"}, reason=" ")
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "reason_required"


def test_broker_blocks_project_escape_before_tool_execution():
    result = CapabilityBroker().call(
        _request("file_read", {"path": "../outside.txt"})
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "path_outside_project"


def test_broker_blocks_immutable_writes():
    result = CapabilityBroker().call(
        _request(
            "file_write",
            {"path": "memory/IMMUTABLE.yaml", "content": "changed"},
        )
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "immutable_path"


def test_broker_fails_closed_for_unknown_capability():
    result = CapabilityBroker().call(
        _request("not_a_capability", {"command": "git status"})
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "unknown_capability"


def test_broker_blocks_not_ready_primitives_by_policy():
    """Risky primitive routes exist but fail before direct execution."""
    result = CapabilityBroker().call(
        _request("shell_run", {"command": "git status"})
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "capability_not_enabled"


def test_broker_auto_routes_registered_capability_keys():
    """Registered tool keys are broker-callable without explicit route wiring."""
    discover_registry_modules()
    broker = CapabilityBroker(discover=False)

    result = broker.call(
        _request("tool.system.inspect", {"include_python": False})
    )

    assert result.success is True
    assert "project_root" in result.data
    assert "tool.system.inspect" in broker.supported_capabilities()
