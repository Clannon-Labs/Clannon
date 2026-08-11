"""
Hermetic tests for api/config_validation.py.

Validates the startup fail-fast config posture: a misconfigured deploy must die
at boot with an actionable message naming ALL bad keys, not just the first.

NO network calls, NO paid LLM keys required. All env interaction is via monkeypatch.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALL_PROVIDER_ENVS = (
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY_2",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
)


def _clear_provider_keys(monkeypatch):
    """Remove all LLM provider keys from the env so the validator sees none."""
    for name in _ALL_PROVIDER_ENVS:
        monkeypatch.delenv(name, raising=False)


def _set_good_env(monkeypatch):
    """Configure a fully-valid production environment."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://clannon.com")
    monkeypatch.setenv("SERVER_COOKIE_SECURE", "1")
    monkeypatch.setenv("SERVER_DB_PATH", "/tmp/test_clannon_val.db")


def _set_strict(monkeypatch):
    monkeypatch.setenv("CLANNON_STRICT_CONFIG", "1")
    monkeypatch.delenv("CLANNON_ENV", raising=False)
    monkeypatch.delenv("VRAKSHA_ENV", raising=False)


# ---------------------------------------------------------------------------
# Import the module under test AFTER monkeypatching happens in each test.
# We import at the top here so the module is loaded once; the functions read
# from os.getenv at call time, so monkeypatching the env is sufficient.
# ---------------------------------------------------------------------------

from api.config_validation import (  # noqa: E402
    ConfigStatus,
    ConfigValidationError,
    fail_fast_if_strict,
    validate_config,
)


# ---------------------------------------------------------------------------
# Core behaviour: strict mode aggregates ALL bad keys
# ---------------------------------------------------------------------------


def test_strict_raises_and_names_all_bad_keys(monkeypatch):
    """In strict mode, a single ConfigValidationError names every offending key,
    not just the first. ACCEPTANCE: the complete-error-list contract."""
    _set_strict(monkeypatch)
    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:3000")  # bad
    monkeypatch.delenv("SERVER_COOKIE_SECURE", raising=False)       # bad (defaults to "0")
    monkeypatch.setenv("SERVER_DB_PATH", "/tmp/test_clannon_val.db")  # good

    with pytest.raises(ConfigValidationError) as exc_info:
        fail_fast_if_strict()

    msg = str(exc_info.value)
    # The aggregated error must name every offender.
    assert "LLM_PROVIDER_KEY" in msg, "aggregated error must name the missing provider key"
    assert "CORS_ORIGINS" in msg,     "aggregated error must name the bad CORS setting"
    assert "SERVER_COOKIE_SECURE" in msg, "aggregated error must name the missing cookie-secure flag"
    # The error is a single exception, not a chain of first-failures.
    assert msg.count("[MISSING]") + msg.count("[MALFORMED]") >= 2


def test_strict_fully_configured_passes(monkeypatch):
    """In strict mode, a fully-configured environment must pass without raising."""
    _set_strict(monkeypatch)
    _set_good_env(monkeypatch)

    fail_fast_if_strict()  # must not raise


def test_strict_single_missing_key_named(monkeypatch):
    """Missing only the provider key in strict mode — error names it explicitly."""
    _set_strict(monkeypatch)
    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://clannon.com")
    monkeypatch.setenv("SERVER_COOKIE_SECURE", "1")
    monkeypatch.setenv("SERVER_DB_PATH", "/tmp/test_clannon_val.db")

    with pytest.raises(ConfigValidationError) as exc_info:
        fail_fast_if_strict()

    msg = str(exc_info.value)
    assert "LLM_PROVIDER_KEY" in msg
    # Should NOT name CORS or COOKIE_SECURE (they are OK)
    assert "CORS_ORIGINS" not in msg
    assert "SERVER_COOKIE_SECURE" not in msg


# ---------------------------------------------------------------------------
# Dev/test default: NEVER raises regardless of missing secrets
# ---------------------------------------------------------------------------


def test_default_never_raises_on_missing_secrets(monkeypatch):
    """Without the strict flag, fail_fast_if_strict() must ONLY warn, never raise —
    even with every provider key absent and CORS pointing to localhost.
    ACCEPTANCE: the hermetic test suite imports config with no real secrets."""
    monkeypatch.delenv("CLANNON_STRICT_CONFIG", raising=False)
    monkeypatch.delenv("CLANNON_ENV", raising=False)
    monkeypatch.delenv("VRAKSHA_ENV", raising=False)
    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:3000")
    monkeypatch.delenv("SERVER_COOKIE_SECURE", raising=False)
    monkeypatch.setenv("SERVER_DB_PATH", "/tmp/test_clannon_val.db")

    fail_fast_if_strict()  # must not raise — only warns via the logger


def test_default_never_raises_with_vraksha_env_dev(monkeypatch):
    """VRAKSHA_ENV=dev (not 'production') must not activate strict mode."""
    monkeypatch.setenv("VRAKSHA_ENV", "dev")
    monkeypatch.delenv("CLANNON_STRICT_CONFIG", raising=False)
    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv("SERVER_DB_PATH", "/tmp/test_clannon_val.db")

    fail_fast_if_strict()  # must not raise


# ---------------------------------------------------------------------------
# Runtime-mode seam: canonical, legacy migration, and tightening override
# ---------------------------------------------------------------------------


def _set_bad_config(monkeypatch):
    """One deterministic config defect that proves whether strictness engaged."""
    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://clannon.com")
    monkeypatch.setenv("SERVER_COOKIE_SECURE", "1")
    monkeypatch.setenv("SERVER_DB_PATH", "/tmp/test_clannon_val.db")


def test_canonical_production_enables_strict_config(monkeypatch):
    monkeypatch.setenv("CLANNON_ENV", "production")
    monkeypatch.delenv("VRAKSHA_ENV", raising=False)
    monkeypatch.delenv("CLANNON_STRICT_CONFIG", raising=False)
    _set_bad_config(monkeypatch)

    with pytest.raises(ConfigValidationError, match="LLM_PROVIDER_KEY"):
        fail_fast_if_strict()


def test_legacy_only_production_remains_strict_during_migration(monkeypatch):
    monkeypatch.delenv("CLANNON_ENV", raising=False)
    monkeypatch.setenv("VRAKSHA_ENV", "production")
    monkeypatch.delenv("CLANNON_STRICT_CONFIG", raising=False)
    _set_bad_config(monkeypatch)

    with pytest.raises(ConfigValidationError, match="LLM_PROVIDER_KEY"):
        fail_fast_if_strict()


def test_canonical_development_does_not_enable_strict_config(monkeypatch):
    monkeypatch.setenv("CLANNON_ENV", "development")
    monkeypatch.delenv("VRAKSHA_ENV", raising=False)
    monkeypatch.delenv("CLANNON_STRICT_CONFIG", raising=False)
    _set_bad_config(monkeypatch)

    fail_fast_if_strict()


def test_unset_runtime_mode_does_not_enable_strict_config(monkeypatch):
    monkeypatch.delenv("CLANNON_ENV", raising=False)
    monkeypatch.delenv("VRAKSHA_ENV", raising=False)
    monkeypatch.delenv("CLANNON_STRICT_CONFIG", raising=False)
    _set_bad_config(monkeypatch)

    fail_fast_if_strict()


def test_force_strict_tightens_development(monkeypatch):
    monkeypatch.setenv("CLANNON_ENV", "development")
    monkeypatch.delenv("VRAKSHA_ENV", raising=False)
    monkeypatch.setenv("CLANNON_STRICT_CONFIG", "true")
    _set_bad_config(monkeypatch)

    with pytest.raises(ConfigValidationError, match="LLM_PROVIDER_KEY"):
        fail_fast_if_strict()


def test_false_strict_override_cannot_loosen_production(monkeypatch):
    monkeypatch.setenv("CLANNON_ENV", "production")
    monkeypatch.delenv("VRAKSHA_ENV", raising=False)
    monkeypatch.setenv("CLANNON_STRICT_CONFIG", "0")
    _set_bad_config(monkeypatch)

    with pytest.raises(ConfigValidationError, match="LLM_PROVIDER_KEY"):
        fail_fast_if_strict()


def test_contradictory_runtime_modes_fail_closed(monkeypatch):
    from foundation import RuntimeEnvironmentError

    monkeypatch.setenv("CLANNON_ENV", "production")
    monkeypatch.setenv("VRAKSHA_ENV", "development")
    monkeypatch.delenv("CLANNON_STRICT_CONFIG", raising=False)

    with pytest.raises(RuntimeEnvironmentError, match="contradictory"):
        fail_fast_if_strict()


@pytest.mark.parametrize("name", ["CLANNON_ENV", "VRAKSHA_ENV"])
def test_invalid_runtime_mode_fails_closed(monkeypatch, name):
    from foundation import RuntimeEnvironmentError

    monkeypatch.delenv("CLANNON_ENV", raising=False)
    monkeypatch.delenv("VRAKSHA_ENV", raising=False)
    monkeypatch.delenv("CLANNON_STRICT_CONFIG", raising=False)
    monkeypatch.setenv(name, "prodution")

    with pytest.raises(RuntimeEnvironmentError, match="unsupported"):
        fail_fast_if_strict()


# ---------------------------------------------------------------------------
# validate_config() structured results
# ---------------------------------------------------------------------------


def test_validate_returns_ok_for_each_good_key(monkeypatch):
    """validate_config() returns ConfigStatus.OK for every key when fully configured."""
    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://clannon.com")
    monkeypatch.setenv("SERVER_COOKIE_SECURE", "1")
    monkeypatch.setenv("SERVER_DB_PATH", "/tmp/test_clannon_val.db")

    checks = validate_config()
    bad = [c for c in checks if c.status != ConfigStatus.OK]
    assert not bad, f"expected all OK; bad: {bad}"


def test_validate_missing_provider_key(monkeypatch):
    """validate_config() reports MISSING for LLM_PROVIDER_KEY with no keys set."""
    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv("SERVER_DB_PATH", "/tmp/test_clannon_val.db")

    checks = validate_config()
    provider_check = next(c for c in checks if c.key == "LLM_PROVIDER_KEY")
    assert provider_check.status == ConfigStatus.MISSING
    # Detail must name at least one env var the operator should set, never a value.
    assert "GOOGLE_API_KEY" in provider_check.detail or "ANTHROPIC_API_KEY" in provider_check.detail


def test_validate_anthropic_key_satisfies_provider_check(monkeypatch):
    """A single Anthropic key is enough to satisfy the provider check."""
    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("SERVER_DB_PATH", "/tmp/test_clannon_val.db")

    checks = validate_config()
    provider_check = next(c for c in checks if c.key == "LLM_PROVIDER_KEY")
    assert provider_check.status == ConfigStatus.OK


def test_validate_cors_wildcard_is_malformed(monkeypatch):
    """A wildcard in CORS_ORIGINS is reported MALFORMED."""
    monkeypatch.setenv("SERVER_CORS_ORIGINS", "*")
    monkeypatch.setenv("SERVER_DB_PATH", "/tmp/test_clannon_val.db")

    checks = validate_config()
    cors_check = next(c for c in checks if c.key == "CORS_ORIGINS")
    assert cors_check.status == ConfigStatus.MALFORMED
    assert "wildcard" in cors_check.detail.lower() or "*" in cors_check.detail


def test_validate_cors_localhost_is_malformed(monkeypatch):
    """A localhost origin in CORS_ORIGINS is MALFORMED (unsafe in production)."""
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:3000")
    monkeypatch.delenv("SERVER_CORS_ORIGINS", raising=False)
    monkeypatch.setenv("SERVER_DB_PATH", "/tmp/test_clannon_val.db")

    checks = validate_config()
    cors_check = next(c for c in checks if c.key == "CORS_ORIGINS")
    assert cors_check.status == ConfigStatus.MALFORMED


def test_validate_cors_production_domain_ok(monkeypatch):
    """A non-localhost HTTPS origin is OK."""
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://app.clannon.com")
    monkeypatch.delenv("SERVER_CORS_ORIGINS", raising=False)
    monkeypatch.setenv("SERVER_DB_PATH", "/tmp/test_clannon_val.db")

    checks = validate_config()
    cors_check = next(c for c in checks if c.key == "CORS_ORIGINS")
    assert cors_check.status == ConfigStatus.OK


def test_validate_cookie_secure_missing_by_default(monkeypatch):
    """Without SERVER_COOKIE_SECURE=1, the check reports MISSING."""
    monkeypatch.delenv("SERVER_COOKIE_SECURE", raising=False)
    monkeypatch.setenv("SERVER_DB_PATH", "/tmp/test_clannon_val.db")

    checks = validate_config()
    cookie_check = next(c for c in checks if c.key == "SERVER_COOKIE_SECURE")
    assert cookie_check.status == ConfigStatus.MISSING


def test_validate_db_path_writable_tmp(monkeypatch):
    """A DB_PATH under /tmp is writable — the check should report OK."""
    monkeypatch.setenv("SERVER_DB_PATH", "/tmp/test_clannon_val.db")

    checks = validate_config()
    db_check = next(c for c in checks if c.key == "SERVER_DB_PATH")
    assert db_check.status == ConfigStatus.OK, f"expected OK: {db_check.detail}"


# ---------------------------------------------------------------------------
# No secret values in error messages
# ---------------------------------------------------------------------------


def test_error_message_never_exposes_key_values(monkeypatch):
    """ConfigValidationError must report key NAMES and presence, never values."""
    _set_strict(monkeypatch)
    _clear_provider_keys(monkeypatch)
    # Set a key so it is present — the value must NOT appear in any output.
    fake_secret = "sk-super-secret-value-that-must-not-appear"
    monkeypatch.setenv("ANTHROPIC_API_KEY", fake_secret)
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:3000")
    monkeypatch.setenv("SERVER_DB_PATH", "/tmp/test_clannon_val.db")

    with pytest.raises(ConfigValidationError) as exc_info:
        fail_fast_if_strict()

    assert fake_secret not in str(exc_info.value)


# ---------------------------------------------------------------------------
# Diagnostic table (printed for visibility in test output)
# ---------------------------------------------------------------------------


def test_validation_table(monkeypatch, capsys):
    """Prints a per-key OK/MISSING/MALFORMED table that documents current defaults."""
    # Simulate a partial configuration (one provider key set; localhost CORS; no cookie-secure).
    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:3000")
    monkeypatch.delenv("SERVER_COOKIE_SECURE", raising=False)
    monkeypatch.setenv("SERVER_DB_PATH", "/tmp/test_clannon_val.db")
    monkeypatch.delenv("CLANNON_STRICT_CONFIG", raising=False)
    monkeypatch.delenv("VRAKSHA_ENV", raising=False)

    checks = validate_config()

    header = f"\n{'Key':<24} {'Status':<12} {'Mode':<26} Detail"
    divider = "-" * 90
    rows = [header, divider]
    for c in checks:
        mode = "STRICT-FAILS-FAST" if c.status != ConfigStatus.OK else "DEFAULT-WARNS-ONLY"
        rows.append(f"{c.key:<24} {c.status.value:<12} {mode:<26} {c.detail}")
    print("\n=== Config Validation Table ===")
    for row in rows:
        print(row)
    print()

    out, _ = capsys.readouterr()
    assert "Config Validation Table" in out
    assert "LLM_PROVIDER_KEY" in out
    assert "CORS_ORIGINS" in out
    assert "SERVER_COOKIE_SECURE" in out
    assert "SERVER_DB_PATH" in out
