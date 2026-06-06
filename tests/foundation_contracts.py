import pytest

from foundation import Flow, Origin, ThreatLevel, ConfigError, constants
from foundation.model_registry import ModelRegistry


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
