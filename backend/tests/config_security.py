"""The security-authorization config (`settings.SecurityConfig` / `config/backend/security.yaml`).

Covers D7's autonomous-action ceiling: the placed value is behavior-preserving (== today's
DEFAULT_AUTONOMOUS_SAFE = {READ}), and the HARD ceiling — a Python constant, not YAML — is
enforced fail-loud: config may only tighten to a subset of {READ}, never loosen past it.
Orchestration wires mission_operate.py to read it; this covers the config seam I own.
"""

import pytest
from pydantic import ValidationError

import settings
from foundation import PermissionLevel
from settings import SecurityConfig


def test_autonomous_ceiling_is_behavior_preserving():
    # Equals today's hardcoded DEFAULT_AUTONOMOUS_SAFE exactly.
    assert settings.SECURITY.autonomous_safe_permissions == frozenset({PermissionLevel.READ})


def test_config_may_tighten_to_a_subset():
    # [] (every action needs approval) and [read] (today) are both within the {READ} ceiling.
    assert SecurityConfig(autonomous_safe_permissions=[]).autonomous_safe_permissions == frozenset()
    assert SecurityConfig(autonomous_safe_permissions=["read"]).autonomous_safe_permissions == frozenset(
        {PermissionLevel.READ}
    )


@pytest.mark.parametrize("beyond", [
    ["read", "write"],   # WRITE is above the ceiling
    ["write"],
    ["execute"],         # EXECUTE/NETWORK/ELEVATED are categorically never autonomous
    ["network"],
    ["elevated"],
])
def test_config_can_never_loosen_past_the_hard_ceiling(beyond):
    # The whole point of D7: a config edit that tries to grant autonomous action beyond {READ}
    # STOPS startup (fail-loud), it does not silently take effect.
    with pytest.raises(ValidationError):
        SecurityConfig(autonomous_safe_permissions=beyond)


def test_the_ceiling_itself_is_not_yaml_overridable():
    # The ceiling is a module constant, not a config field — there is no key to raise it from YAML.
    assert settings._AUTONOMOUS_SAFE_CEILING == frozenset({PermissionLevel.READ})
    with pytest.raises(ValidationError):
        SecurityConfig(autonomous_safe_permissions=["read"], ceiling=["read", "write"])  # extra key


def test_unknown_permission_name_is_rejected():
    with pytest.raises(ValidationError):
        SecurityConfig(autonomous_safe_permissions=["superuser"])
