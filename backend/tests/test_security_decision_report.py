"""
Acceptance tests for scripts/benchmarks/security_decision_report.py.

Pins the security-validation demo scene: every adversarial payload is blocked at the
verifier with the correct audit code, every benign control passes, and the human-readable
report renders the expected structural sections. Hermetic — no network, no model key.
"""

from __future__ import annotations

import importlib.util
import sys
import time
import types
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load the demo script as a module (it lives in scripts/, not a package).
# ---------------------------------------------------------------------------
_BACKEND = Path(__file__).resolve().parents[1]
_SCRIPT = _BACKEND / "scripts" / "benchmarks" / "security_decision_report.py"


def _load_demo():
    _MOD_NAME = "security_decision_report"
    if _MOD_NAME in sys.modules:
        return sys.modules[_MOD_NAME]
    spec = importlib.util.spec_from_file_location(_MOD_NAME, _SCRIPT)
    if spec is None or spec.loader is None:
        pytest.skip(f"cannot load {_SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so @dataclass string annotations resolve correctly.
    sys.modules[_MOD_NAME] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture(scope="module")
def demo():
    return _load_demo()


@pytest.fixture(scope="module")
def results(demo):
    decisions, report = demo.run()
    return decisions, report


# ---------------------------------------------------------------------------
# Battery completeness
# ---------------------------------------------------------------------------


def test_battery_has_attacks_and_benign(demo):
    fixtures = demo.battery()
    attacks = [f for f in fixtures if f.is_attack]
    benign = [f for f in fixtures if not f.is_attack]
    assert len(attacks) >= 6, f"expected >=6 attacks, got {len(attacks)}"
    assert len(benign) >= 4, f"expected >=4 benign controls, got {len(benign)}"


def test_battery_reuses_prompt_regression_fixtures(demo):
    fixtures = demo.battery()
    from_pr = [f for f in fixtures if f.id.startswith("pr:")]
    assert from_pr, "no prompt_regression fixtures loaded into the battery"


# ---------------------------------------------------------------------------
# Blocking correctness
# ---------------------------------------------------------------------------


def test_every_attack_is_blocked(results):
    decisions, _ = results
    attacks = [d for d in decisions if d.fixture.is_attack]
    assert attacks, "battery has no attack payloads"
    for d in attacks:
        assert d.blocked, (
            f"{d.fixture.id} was NOT blocked — the pipeline passed a known adversarial input"
        )


def test_every_attack_blocked_at_verifier(results):
    decisions, _ = results
    for d in (d for d in decisions if d.fixture.is_attack):
        assert d.origin == "verifier", (
            f"{d.fixture.id} blocked at {d.origin!r}, expected 'verifier'"
        )


def test_every_attack_has_high_threat(results):
    decisions, _ = results
    for d in (d for d in decisions if d.fixture.is_attack):
        assert d.threat_level == "high", (
            f"{d.fixture.id} threat_level={d.threat_level!r}, expected 'high'"
        )


def test_every_attack_carries_a_block_code(results):
    decisions, _ = results
    valid_codes = {
        "injection_detected",
        "verifier_rejected",
        "malicious_content",
        "unsupported_modality",
    }
    for d in (d for d in decisions if d.fixture.is_attack):
        assert d.block_code in valid_codes, (
            f"{d.fixture.id} block_code={d.block_code!r} is not a recognised audit reason code"
        )


def test_every_attack_block_code_matches_expected(results):
    decisions, _ = results
    for d in (d for d in decisions if d.fixture.is_attack and d.fixture.expected_block_reason):
        assert d.block_code == d.fixture.expected_block_reason, (
            f"{d.fixture.id}: got block_code={d.block_code!r}, "
            f"expected {d.fixture.expected_block_reason!r}"
        )


def test_every_attack_carries_a_reason(results):
    decisions, _ = results
    for d in (d for d in decisions if d.fixture.is_attack):
        assert d.reason, f"{d.fixture.id} block carries no human-readable reason"


def test_every_attack_carries_categories(results):
    decisions, _ = results
    for d in (d for d in decisions if d.fixture.is_attack):
        assert d.categories, f"{d.fixture.id} blocked without any classification categories"


# ---------------------------------------------------------------------------
# Benign controls — no false-positive wall
# ---------------------------------------------------------------------------


def test_benign_controls_are_not_blocked(results):
    decisions, _ = results
    benign = [d for d in decisions if not d.fixture.is_attack]
    assert benign, "battery has no benign controls"
    for d in benign:
        assert not d.blocked, (
            f"benign control {d.fixture.id!r} was blocked "
            f"(code={d.block_code!r}); the deterministic regex must stay a HINT"
        )


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def test_report_renders_structural_sections(results):
    _, report = results
    assert "CLANNON" in report
    assert "SECURITY VALIDATION" in report
    assert "SUMMARY" in report
    assert "Attacks blocked:" in report
    assert "Benign controls:" in report


def test_report_contains_every_fixture_id(results, demo):
    _, report = results
    for f in demo.battery():
        assert f.id in report, f"fixture {f.id!r} missing from rendered report"


def test_report_verdict_is_pass(results):
    _, report = results
    assert "C5 SECURITY VALIDATION: PASS" in report, (
        "expected PASS verdict in the security validation report"
    )


def test_main_returns_zero(demo):
    rc = demo.main()
    assert rc == 0, f"main() returned {rc!r} — some attacks were not blocked or benign controls were"


# ---------------------------------------------------------------------------
# Durable-path test — exercises _persist_to_audit_trail, _read_back_from_audit_trail,
# and the rec['id']/rec['blocked_at']:.0f render branch that no other test reaches.
# ---------------------------------------------------------------------------

_SDR_DURABLE_MOD_NAME = "_sdr_with_audit"


def _build_fake_audit_module():
    """Build a fake api.audit module with in-memory record storage."""
    _store: dict[str, list[dict]] = {}

    def write_block_record(
        *,
        user_id: str,
        session_id: str,
        trace_id: str,
        block_code: str,
        threat_level: str,
        origin: str,
        reason: str | None,
    ) -> None:
        _store.setdefault(trace_id, []).append(
            {
                "id": f"rec-{trace_id[:12]}",
                "blocked_at": time.time(),
                "trace_id": trace_id,
                "block_code": block_code,
                "threat_level": threat_level,
                "origin": origin,
                "reason": reason,
            }
        )

    def get_for_run(user_id: str, trace_id: str) -> list[dict]:
        return _store.get(trace_id, [])

    mod = types.ModuleType("api.audit")
    mod.write_block_record = write_block_record  # type: ignore[attr-defined]
    mod.get_for_run = get_for_run  # type: ignore[attr-defined]
    return mod, _store


@pytest.fixture
def demo_durable():
    """Load a fresh copy of the demo with a fake api.audit injected into sys.modules."""
    fake_audit_mod, store = _build_fake_audit_module()

    # Inject the fake BEFORE loading the demo so the module-level try/import picks it up.
    old_api_audit = sys.modules.get("api.audit")
    sys.modules["api.audit"] = fake_audit_mod

    sys.modules.pop(_SDR_DURABLE_MOD_NAME, None)
    spec = importlib.util.spec_from_file_location(_SDR_DURABLE_MOD_NAME, _SCRIPT)
    if spec is None or spec.loader is None:
        sys.modules.pop("api.audit", None)
        pytest.skip("cannot load demo for durable-path test")

    mod = importlib.util.module_from_spec(spec)
    sys.modules[_SDR_DURABLE_MOD_NAME] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    yield mod, store

    # Restore sys.modules to pre-test state.
    sys.modules.pop(_SDR_DURABLE_MOD_NAME, None)
    if old_api_audit is None:
        sys.modules.pop("api.audit", None)
    else:
        sys.modules["api.audit"] = old_api_audit


def test_durable_path_record_and_query_cycle(demo_durable):
    """
    Verify the full durable record-and-query cycle when api.audit is available.

    Exercises _persist_to_audit_trail, _read_back_from_audit_trail, and the
    rec['id']/rec['blocked_at']:.0f render branch that no other test reaches.
    Injects a faithful fake api.audit — same signatures as the sibling
    feat/c5-security-audit-trail branch — so the test runs without that branch merged.
    """
    mod, _store = demo_durable

    assert mod._AUDIT_AVAILABLE, (
        "fake api.audit was not picked up at module load — _AUDIT_AVAILABLE is False; "
        "check that the injection happens before spec.loader.exec_module"
    )

    decisions, report = mod.run()

    blocked = [d for d in decisions if d.blocked]
    assert blocked, "battery produced no blocked decisions — the durable-path test is vacuous"

    # Every blocked decision must have at least one audit record read back.
    for d in blocked:
        assert d.audit_records, (
            f"{d.fixture.id}: audit_records is empty — "
            "_persist_to_audit_trail or _read_back_from_audit_trail did not fire"
        )
        rec = d.audit_records[0]
        assert "id" in rec, f"{d.fixture.id}: audit record is missing the 'id' key"
        assert "blocked_at" in rec, f"{d.fixture.id}: audit record is missing the 'blocked_at' key"
        assert isinstance(rec["blocked_at"], float), (
            f"{d.fixture.id}: 'blocked_at' must be a float so the :.0f format succeeds"
        )

    # Banner must reflect actual read-back, not just import presence.
    assert "DURABLE" in report, (
        "report banner does not say DURABLE even though audit records were read back"
    )

    # The per-payload rec['id'] / rec['blocked_at']:.0f render branch must fire.
    assert "Audit:   record" in report, (
        "report is missing 'Audit:   record ...' — the per-payload durable-record line was not rendered"
    )
    assert "blockedAt=" in report, (
        "report is missing 'blockedAt=' — the per-payload durable-record line was not rendered"
    )
