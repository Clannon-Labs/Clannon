"""
Startup configuration validator.

Closes the fail-open posture: api/config.py loads every setting via os.getenv()
with silent defaults and has no validation; provider keys are checked only at
first LLM use (core/llm/registry.py:84-93), so a misconfigured deploy boots
"healthy" and fails mid-run.

This module provides two callables:

    validate_config()      -> list[ConfigCheck]
        Always safe to call; never raises; never has side effects.
        Returns a per-key structured result (OK / MISSING / MALFORMED).

    fail_fast_if_strict()  -> None
        Call once at startup (api/app.py does this).
        In strict/prod mode (VRAKSHA_ENV=production OR CLANNON_STRICT_CONFIG=1):
            raises ConfigValidationError naming ALL bad keys at once — a bad
            deploy dies at boot with an actionable message, not mid-run.
        In dev/test default:
            logs warnings only, never raises — the hermetic test suite imports
            config with no real secrets and must remain unaffected.

The strict flag mirrors the existing fail-closed prod-guard precedent used by
security/sanitizers/pre_sanitization.py (VRAKSHA_ENV / AGENT_REQUIRE_YARA).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum

_log = logging.getLogger("clannon.config")


class ConfigStatus(str, Enum):
    OK = "OK"
    MISSING = "MISSING"
    MALFORMED = "MALFORMED"


@dataclass(frozen=True)
class ConfigCheck:
    """One configuration key's validation result. Never carries secret values."""
    key: str
    status: ConfigStatus
    detail: str


class ConfigValidationError(RuntimeError):
    """Raised at boot in strict mode when required config is absent or malformed.
    Aggregates ALL bad keys so a single error message is actionable."""

    def __init__(self, checks: list[ConfigCheck]) -> None:
        bad = [c for c in checks if c.status != ConfigStatus.OK]
        lines = ["Startup config validation failed — fix these before deploying:"]
        for c in bad:
            lines.append(f"  [{c.status.value}] {c.key}: {c.detail}")
        super().__init__("\n".join(lines))
        self.checks = checks


def _is_strict() -> bool:
    """True in production/strict mode. Mirrors the VRAKSHA_ENV pattern from
    security/sanitizers/pre_sanitization.py:40-43."""
    return (
        os.getenv("VRAKSHA_ENV", "").strip().lower() in {"prod", "production"}
        or os.getenv("CLANNON_STRICT_CONFIG", "").strip().lower() in {"1", "true", "yes"}
    )


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_llm_providers() -> ConfigCheck:
    """At least one LLM provider credential must exist for the configured routing.

    Reuses core/llm/registry._provider_available — the canonical source of truth
    for whether a provider's key is present; does not duplicate or change its logic.
    """
    # Deferred import: avoids paying models.yaml load at module import time
    # and keeps this module cheap as a standalone import.
    from core.llm.registry import _provider_available  # type: ignore[attr-defined]

    available = any(
        _provider_available(f"{provider}:check")
        for provider in ("google", "anthropic", "openai")
    )
    if available:
        return ConfigCheck(
            "LLM_PROVIDER_KEY",
            ConfigStatus.OK,
            "at least one provider key is set",
        )
    return ConfigCheck(
        "LLM_PROVIDER_KEY",
        ConfigStatus.MISSING,
        "no API key found for google / anthropic / openai — set at least one of "
        "GOOGLE_API_KEY, GEMINI_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY",
    )


def _check_cors() -> ConfigCheck:
    """Effective CORS origins must not be a wildcard or point to localhost.

    Reads from env at call time (not from the already-evaluated api.config constants)
    so tests can monkeypatch the env without reloading modules. The effective origins
    mirror config.py:19-21: SERVER_CORS_ORIGINS wins; FRONTEND_ORIGIN is the fallback.
    Does NOT change how CORS is applied — that is api/app.py's responsibility.
    """
    origins_env = os.getenv("SERVER_CORS_ORIGINS", "").strip()
    frontend_env = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
    raw = origins_env if origins_env else frontend_env
    origins = [o.strip() for o in raw.split(",") if o.strip()]

    if not origins:
        return ConfigCheck("CORS_ORIGINS", ConfigStatus.MISSING, "no CORS origins configured")

    if "*" in origins:
        return ConfigCheck(
            "CORS_ORIGINS",
            ConfigStatus.MALFORMED,
            "CORS_ORIGINS contains wildcard '*' — set an explicit allowlist in production",
        )

    localhost_count = sum(
        1 for o in origins if "localhost" in o or "127.0.0.1" in o
    )
    if localhost_count:
        return ConfigCheck(
            "CORS_ORIGINS",
            ConfigStatus.MALFORMED,
            f"{localhost_count} origin(s) reference localhost — set production domains via "
            "FRONTEND_ORIGIN or SERVER_CORS_ORIGINS",
        )

    return ConfigCheck(
        "CORS_ORIGINS",
        ConfigStatus.OK,
        f"{len(origins)} non-localhost origin(s) configured",
    )


def _check_cookie_secure() -> ConfigCheck:
    """In production, SERVER_COOKIE_SECURE must be '1' so session cookies are
    only sent over HTTPS and cannot be intercepted in transit."""
    if os.getenv("SERVER_COOKIE_SECURE", "0") == "1":
        return ConfigCheck("SERVER_COOKIE_SECURE", ConfigStatus.OK, "secure cookies enabled")
    return ConfigCheck(
        "SERVER_COOKIE_SECURE",
        ConfigStatus.MISSING,
        "SERVER_COOKIE_SECURE is not '1' — session cookies will be sent over plain HTTP",
    )


def _check_db_path() -> ConfigCheck:
    """The DB_PATH parent directory must be writable (or creatable).

    Reads SERVER_DB_PATH from env first (tests can monkeypatch this);
    falls back to the already-computed api.config.DB_PATH constant.
    """
    db_path = os.getenv("SERVER_DB_PATH")
    if not db_path:
        from api import config as _cfg  # deferred; api.config may not be imported yet

        db_path = _cfg.DB_PATH

    if not db_path:
        return ConfigCheck("SERVER_DB_PATH", ConfigStatus.MISSING, "DB_PATH is not set")

    parent = os.path.dirname(os.path.abspath(db_path))
    if os.path.exists(parent):
        writable = os.access(parent, os.W_OK)
    else:
        grandparent = os.path.dirname(parent)
        writable = (
            bool(grandparent)
            and os.path.exists(grandparent)
            and os.access(grandparent, os.W_OK)
        )

    if not writable:
        return ConfigCheck(
            "SERVER_DB_PATH",
            ConfigStatus.MALFORMED,
            f"storage directory is not writable — check permissions for {parent}",
        )
    return ConfigCheck("SERVER_DB_PATH", ConfigStatus.OK, "storage path is writable")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_config() -> list[ConfigCheck]:
    """Run all startup config checks.

    Always safe to call: never raises, never writes anything, has no side effects.
    Returns one ConfigCheck per key — callers can filter by status.
    """
    return [
        _check_llm_providers(),
        _check_cors(),
        _check_cookie_secure(),
        _check_db_path(),
    ]


def fail_fast_if_strict() -> None:
    """Validate startup config and enforce it in strict/production mode.

    Logs a warning for every non-OK check regardless of mode.
    In strict mode (VRAKSHA_ENV=production OR CLANNON_STRICT_CONFIG=1/true/yes):
        raises ConfigValidationError naming ALL bad keys at once so the operator
        sees every problem in one message, not just the first.
    In dev/test default (no strict flag):
        logs warnings only, never raises — the hermetic test suite which imports
        config with no real secrets is completely unaffected.
    """
    strict = _is_strict()
    checks = validate_config()
    bad = [c for c in checks if c.status != ConfigStatus.OK]

    if not bad:
        _log.info("config validation passed (%d checks OK)", len(checks))
        return

    for c in bad:
        _log.warning("config [%s] %s: %s", c.status.value, c.key, c.detail)

    if strict:
        raise ConfigValidationError(checks)
    # dev/test default: already logged above, continue startup
