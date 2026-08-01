"""Focused contract tests for the deterministic ``time.current_time`` tool."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from foundation import PermissionLevel
from registry.capabilities import discover, registry
from tools.time import CurrentTimeIn, CurrentTimeOut, CurrentTimeTool


def _current_time(target_zone: str | None = None) -> CurrentTimeOut:
    return asyncio.run(CurrentTimeTool().run(CurrentTimeIn(target_zone=target_zone)))


def _assert_captured_now(result: CurrentTimeOut, before: datetime, after: datetime) -> datetime:
    parsed = datetime.fromisoformat(result.result)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() is not None
    assert before <= parsed.astimezone(timezone.utc) <= after
    return parsed


def test_current_time_is_discoverable_with_read_permission_and_guided_schemas():
    discover()
    spec = registry.get_tool("time.current_time")

    assert spec is not None
    assert "time.current_time" not in {broken.key for broken in registry.broken()}
    assert spec.permission == PermissionLevel.READ
    assert spec.input_schema is CurrentTimeIn
    assert spec.output_schema is CurrentTimeOut
    assert spec.eager is False
    assert "current date and time" in spec.description
    assert "defaults to UTC" in spec.description
    assert "convert" not in spec.description.lower()

    target_zone_schema = spec.input_schema.model_json_schema()["properties"]["target_zone"]
    assert target_zone_schema["default"] is None
    assert "IANA timezone" in target_zone_schema["description"]
    assert "Asia/Kathmandu" in target_zone_schema["description"]
    assert "omitted means UTC" in target_zone_schema["description"]

    output_properties = spec.output_schema.model_json_schema()["properties"]
    assert "timezone-aware" in output_properties["result"]["description"]
    assert "UTC" in output_properties["zone_used"]["description"]


def test_omitted_zone_returns_current_aware_utc_time():
    before = datetime.now(timezone.utc)
    result = _current_time()
    after = datetime.now(timezone.utc)

    parsed = _assert_captured_now(result, before, after)
    assert result.zone_used == "UTC"
    assert parsed.utcoffset() == timedelta(0)


def test_valid_iana_zone_returns_current_time_with_zone_and_offset():
    before = datetime.now(timezone.utc)
    result = _current_time("Asia/Kathmandu")
    after = datetime.now(timezone.utc)

    parsed = _assert_captured_now(result, before, after)
    assert result.zone_used == "Asia/Kathmandu"
    assert parsed.utcoffset() == timedelta(hours=5, minutes=45)


def test_invalid_iana_zone_fails_explicitly():
    with pytest.raises(ValueError, match=r"^Unknown IANA timezone: Not/A_Real_Zone$"):
        _current_time("Not/A_Real_Zone")
