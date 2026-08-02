import ast
import asyncio
from dataclasses import FrozenInstanceError

import pytest

import foundation
from foundation import (
    Flow, Origin, ThreatLevel, ConfigError, constants,
    BudgetScope, TokenBudget, BudgetReservation, BudgetPort, BudgetExhausted,
    InfrastructureError, VrakshaError,
)
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


@pytest.mark.parametrize("blank", [TimeoutError(), asyncio.CancelledError(), Exception("")])
def test_flow_fail_never_records_an_empty_reason(blank):
    """A fail-closed stage must always be able to say what closed it.

    `str(exc)` is empty for exceptions raised without a message, and the live
    path is a sanitizer worker timeout (`security/sanitizers/runner.py:128`):
    the run was correctly refused and the journal recorded `''`. An operator
    reading that cannot tell a timeout from a crash from a bug in the recorder
    itself, which is the "degrade honestly" law failing exactly where it counts.

    Asserted on all three surfaces the fault travels through, because recording
    it in one and losing it in another is the same outage for whoever is reading.
    """
    out = Flow.new("x", "s").fail(blank, Origin.SANITIZER)
    assert out.error == type(blank).__name__
    assert out.journal[-1].error == type(blank).__name__
    assert out.ctx.failure_error == type(blank).__name__


def test_flow_fail_keeps_an_exception_message_verbatim():
    """The floor must not become a rewrite.

    Every existing journal entry, API error field and assertion reads this
    string, so a message-carrying exception has to survive unchanged — the
    empty case is the only behaviour that was allowed to change.
    """
    out = Flow.new("x", "s").fail(InfrastructureError("qdrant refused the connection"), Origin.INTAKE)
    assert out.error == "qdrant refused the connection"


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


# --- budget contract (foundation/contracts/budget.py) — inert seam, no impl yet ---

def test_budget_scope_defaults_and_is_frozen():
    scope = BudgetScope(user_id="u1")
    assert scope.mission_id == ""                 # user-only turn: no mission ceiling
    with pytest.raises(FrozenInstanceError):
        scope.user_id = "attacker"                # identity-set-once: immutable


def test_token_budget_defaults():
    budget = TokenBudget(user_remaining=1000)
    assert budget.mission_remaining is None       # None = no mission ceiling in play
    assert budget.period == ""


def test_budget_reservation_carries_scope_and_estimate():
    scope = BudgetScope(user_id="u1", mission_id="m1")
    res = BudgetReservation(reservation_id="r1", scope=scope, estimated=500)
    assert res.scope.mission_id == "m1"
    assert res.estimated == 500


def test_budget_port_is_runtime_checkable():
    class _Impl:
        async def reserve(self, scope, estimate): ...
        async def reconcile(self, reservation, actual): ...
        async def remaining(self, scope): ...

    assert isinstance(_Impl(), BudgetPort)         # duck-typed sole broker satisfies it
    assert not isinstance(object(), BudgetPort)    # missing the door → not a BudgetPort


def test_budget_exhausted_is_infrastructure_and_carries_context():
    err = BudgetExhausted(
        "user billing ceiling reached", ceiling="user", retry_after=3600.0,
    )
    assert isinstance(err, InfrastructureError)    # 4xx: fail-closed resource refusal
    assert isinstance(err, VrakshaError)
    assert err.ceiling == "user"
    assert err.retry_after == 3600.0
    assert "ceiling=user" in str(err) and "retry_after=3600.0s" in str(err)


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
