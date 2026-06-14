import pytest

from foundation import Flow, Origin, ThreatLevel, ConfigError, constants
from registry.config import ModelRegistry


def test_flow_truncates_long_error():
    out = Flow.new("x", "s").fail(Exception("E" * 5000), Origin.INTAKE)
    assert len(out.error) <= constants.MAX_ERROR_LENGTH + 1  # +1 for the ellipsis


def test_flow_truncates_long_warn_reason():
    out = Flow.new("x", "s").warn("R" * 5000, ThreatLevel.LOW, Origin.VERIFIER)
    assert len(out.reason) <= constants.MAX_REASON_LENGTH + 1


def test_explicit_route_overrides_defaults():
    cfg = {
        "defaults": {"provider": "google", "verifier": "google"},
        "routes": {"verifier": "openai"},
        "google": {"verifier": {"model": "g"}},
        "openai": {"verifier": {"model": "o"}},
    }
    registry = ModelRegistry(cfg)
    profile = registry.for_role("verifier")
    assert profile.provider == "openai"
    assert profile.model == "o"


def test_config_error_on_unknown_provider():
    registry = ModelRegistry({"defaults": {"provider": "does-not-exist"}})
    with pytest.raises(ConfigError):
        registry.for_role("verifier")


def test_config_error_on_missing_role():
    registry = ModelRegistry({"defaults": {"provider": "google"}, "google": {}})
    with pytest.raises(ConfigError):
        registry.for_role("verifier")


def test_flow_sub_millisecond_duration_is_still_recorded():
    import time
    flow = Flow.new("x", "s")
    out = flow.next("y", Origin.INTAKE, started_at=time.monotonic())  # ~0.0ms
    assert out.meta.duration_ms is not None
    assert out.journal[-1].duration_ms is not None


def test_flow_block_and_fail_release_the_cached_payload():
    import asyncio

    async def go():
        flow = Flow.new(b"big malicious buffer", "s")
        await flow.load()                       # cache it, as a stage would
        blocked = flow.block(
            __import__("foundation").BlockReason.MALICIOUS_CONTENT,
            ThreatLevel.HIGH, Origin.SANITIZER,
        )
        assert blocked.handle._cached is None   # released — nothing downstream loads it

        flow2 = Flow.new(b"payload", "s")
        await flow2.load()
        failed = flow2.fail(Exception("infra"), Origin.SANITIZER)
        assert failed.handle._cached is None

    asyncio.run(go())
