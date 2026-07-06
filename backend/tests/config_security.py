"""The security-authorization config (`settings.SecurityConfig` / `config/backend/security.yaml`).

Covers the D7 autonomous-action ceiling AND the D8 sandbox caps. The shared property: some
values are HARD-CEILINGED by a Python constant (not YAML) — config may only TIGHTEN, never
loosen past a safe bound, and a raising edit fails LOUD at load. The sandbox caps are NUMBERS
(not docker "512m" strings) precisely so the ceiling check can't be fail-open. Consumers are
wired by orchestration; this covers the config seam I own.
"""

import pytest
from pydantic import ValidationError

import settings
from foundation import PermissionLevel
from settings import SecurityConfig


def _kw(**over):
    """All required SecurityConfig fields at today's values; override what a test exercises."""
    base = dict(
        autonomous_safe_permissions=["read"],
        sandbox_memory_mb=512, sandbox_cpus=1.0, sandbox_pids=256, sandbox_tmpfs_mb=64,
        sandbox_run_timeout_s=60.0, sandbox_max_output_chars=20000,
        sandbox_create_timeout_s=180.0, sandbox_teardown_timeout_s=20.0,
    )
    return {**base, **over}


# ── D7 autonomous-action ceiling ────────────────────────────────────────────────────────────

def test_autonomous_ceiling_is_behavior_preserving():
    assert settings.SECURITY.autonomous_safe_permissions == frozenset({PermissionLevel.READ})


def test_config_may_tighten_autonomy_to_a_subset():
    assert SecurityConfig(**_kw(autonomous_safe_permissions=[])).autonomous_safe_permissions == frozenset()
    assert SecurityConfig(**_kw(autonomous_safe_permissions=["read"])).autonomous_safe_permissions == frozenset(
        {PermissionLevel.READ}
    )


@pytest.mark.parametrize("beyond", [["read", "write"], ["write"], ["execute"], ["network"], ["elevated"]])
def test_autonomy_can_never_loosen_past_read(beyond):
    with pytest.raises(ValidationError):
        SecurityConfig(**_kw(autonomous_safe_permissions=beyond))


def test_autonomy_ceiling_not_yaml_overridable():
    assert settings._AUTONOMOUS_SAFE_CEILING == frozenset({PermissionLevel.READ})
    with pytest.raises(ValidationError):
        SecurityConfig(**_kw(ceiling=["read", "write"]))   # extra key


def test_unknown_permission_name_rejected():
    with pytest.raises(ValidationError):
        SecurityConfig(**_kw(autonomous_safe_permissions=["superuser"]))


# ── D8 sandbox caps ─────────────────────────────────────────────────────────────────────────

def test_sandbox_caps_behavior_preserving():
    s = settings.SECURITY
    assert (s.sandbox_memory_mb, s.sandbox_cpus, s.sandbox_pids, s.sandbox_tmpfs_mb) == (512, 1.0, 256, 64)
    assert (s.sandbox_run_timeout_s, s.sandbox_max_output_chars) == (60.0, 20000)
    assert (s.sandbox_create_timeout_s, s.sandbox_teardown_timeout_s) == (180.0, 20.0)


@pytest.mark.parametrize("tighter", [
    {"sandbox_memory_mb": 256}, {"sandbox_cpus": 0.5}, {"sandbox_pids": 128},
    {"sandbox_run_timeout_s": 30.0}, {"sandbox_max_output_chars": 5000},
])
def test_sandbox_config_may_tighten(tighter):
    SecurityConfig(**_kw(**tighter))  # lowering a cap = stricter sandbox = allowed


@pytest.mark.parametrize("looser", [
    {"sandbox_memory_mb": 1024},        # the fail-OPEN string bug this guards against
    {"sandbox_cpus": 2.0},
    {"sandbox_pids": 512},
    {"sandbox_tmpfs_mb": 128},
    {"sandbox_run_timeout_s": 120.0},
    {"sandbox_max_output_chars": 999999},
])
def test_sandbox_config_can_never_loosen_past_the_ceiling(looser):
    # A config edit that would grant the sandbox MORE than today STOPS startup — never silently
    # weakens isolation (the whole reason these are numbers, not "512m" strings).
    with pytest.raises(ValidationError):
        SecurityConfig(**_kw(**looser))


@pytest.mark.parametrize("ops", [{"sandbox_create_timeout_s": 999.0}, {"sandbox_teardown_timeout_s": 999.0}])
def test_ops_timeouts_have_no_ceiling(ops):
    # These bound our own wait on the docker CLI, not the workload — no security direction.
    SecurityConfig(**_kw(**ops))
