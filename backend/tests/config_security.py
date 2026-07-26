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
        sanitizer_timeout_total_s=15.0, sanitizer_timeout_worker_s=10.0, sanitizer_max_workers=10,
        filter_max_retries=2,
        pii_redacted_entities=[
            "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "IBAN_CODE", "US_BANK_NUMBER",
            "US_SSN", "US_ITIN", "US_PASSPORT", "US_DRIVER_LICENSE", "UK_NHS",
            "MEDICAL_LICENSE", "CRYPTO", "IP_ADDRESS",
        ],
        filter_grounding_max_findings=8, filter_grounding_max_finding_chars=1500,
        filter_grounding_max_tool_calls=12, filter_grounding_max_tool_result_chars=1200,
        archive_max_entries=10000, archive_max_uncompressed_ratio=20,
        max_workspace_snapshot_bytes=200 * 1024 * 1024,
    )
    return {**base, **over}


# ── D8 security config: PII floor + filter grounding floor/ceiling ──────────────────────────────

def test_pii_config_can_add_but_not_drop_a_baseline_entity():
    from settings import SecurityConfig
    # adding one is fine
    SecurityConfig(**_kw(pii_redacted_entities=_kw()["pii_redacted_entities"] + ["LOCATION"]))
    # dropping a baseline entity fails loud
    dropped = [e for e in _kw()["pii_redacted_entities"] if e != "US_SSN"]
    with pytest.raises(ValidationError):
        SecurityConfig(**_kw(pii_redacted_entities=dropped))


def test_filter_grounding_may_widen_within_ceiling_but_not_narrow_or_blow_up():
    from settings import SecurityConfig
    SecurityConfig(**_kw(filter_grounding_max_findings=16))   # widen (<=32) ok
    SecurityConfig(**_kw(filter_grounding_max_findings=32))   # ceiling ok
    with pytest.raises(ValidationError):
        SecurityConfig(**_kw(filter_grounding_max_findings=4))    # below floor 8
    with pytest.raises(ValidationError):
        SecurityConfig(**_kw(filter_grounding_max_findings=33))   # above ceiling 32


def test_security_config_d8_values_loaded():
    s = settings.SECURITY
    assert s.sanitizer_max_workers == 10 and s.filter_max_retries == 2
    assert "US_SSN" in s.pii_redacted_entities
    assert s.filter_grounding_max_findings == 8


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


def test_archive_bomb_guards_may_tighten_but_not_loosen_past_ceiling():
    # D8 (security review 2026-07-25): config may LOWER a bomb guard (tighter), never RAISE it past
    # the ceiling (looser = more bomb surface).
    SecurityConfig(**_kw(archive_max_entries=5000))      # tighter — ok
    SecurityConfig(**_kw(archive_max_entries=10000))     # at ceiling — ok
    with pytest.raises(ValidationError):
        SecurityConfig(**_kw(archive_max_entries=20000))            # loosen past ceiling — rejected
    with pytest.raises(ValidationError):
        SecurityConfig(**_kw(archive_max_uncompressed_ratio=100))   # loosen past ceiling — rejected


def test_workspace_snapshot_cap_may_tighten_but_not_loosen_past_ceiling():
    # Cross-call workspace persistence (orchestration proposal 2026-07-26 §4): same D8
    # ceiling discipline as the archive bomb guards, absolute rather than ratio.
    SecurityConfig(**_kw(max_workspace_snapshot_bytes=50 * 1024 * 1024))    # tighter — ok
    SecurityConfig(**_kw(max_workspace_snapshot_bytes=200 * 1024 * 1024))   # at ceiling — ok
    with pytest.raises(ValidationError):
        SecurityConfig(**_kw(max_workspace_snapshot_bytes=400 * 1024 * 1024))  # loosen — rejected


def test_workspace_snapshot_cap_loaded():
    assert settings.SECURITY.max_workspace_snapshot_bytes == 200 * 1024 * 1024
