import ast

import pytest

import foundation
from foundation import Flow, Origin, ThreatLevel, ConfigError, constants
from registry.config import ModelRegistry


def _names_bound_by_import_block():
    """Names the public surface re-exports, read straight from the import block.

    Parses `foundation/__init__.py` and collects every name bound by a relative
    `from .X import (...)` statement (its alias if aliased). This is exactly the
    set `__all__` is meant to mirror; `__future__` and star imports are ignored.
    """
    source = open(foundation.__file__, encoding="utf-8").read()
    bound = set()
    for node in ast.parse(source).body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level == 0 or node.module == "__future__":
            continue
        for alias in node.names:
            if alias.name != "*":
                bound.add(alias.asname or alias.name)
    return bound


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


def test_all_mirrors_the_import_block():
    """__all__ is the public surface; it must list exactly what the import block
    re-exports. Catches an import added or removed without updating __all__."""
    exported = set(foundation.__all__)
    imported = _names_bound_by_import_block()

    missing = imported - exported          # imported but not advertised
    stale = exported - imported            # advertised but no longer imported
    assert not missing, f"in the import block but missing from __all__: {sorted(missing)}"
    assert not stale, f"in __all__ but not imported: {sorted(stale)}"


def test_all_has_no_duplicates():
    assert len(foundation.__all__) == len(set(foundation.__all__))


def test_every_all_entry_resolves_on_the_module():
    """`from foundation import X` works for every advertised name."""
    unresolved = [name for name in foundation.__all__ if not hasattr(foundation, name)]
    assert not unresolved, f"listed in __all__ but absent from the module: {unresolved}"
