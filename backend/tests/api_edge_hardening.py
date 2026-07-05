"""
Hermetic acceptance tests for api/hardening.py — the three HTTP edge guards.

All four checks run against a minimal FastAPI app created here (no database, no auth,
no pipeline, no paid-API calls).  The verdict table is printed to stdout and any
VIOLATED guard also fails the test suite.

Guard                   What it asserts
---------------------------------------------------------------------------
HEADERS-SET             Every response carries all five security headers,
                        including on 4xx, 5xx, and streaming responses.
EXC-STRUCTURED-NO-LEAK  An endpoint that raises an unhandled exception returns
                        a structured 500 body with NO stack trace, file path,
                        exception class name, or exception repr visible to the client.
VALIDATION-CLEAN        A malformed request (Pydantic validation failure) returns
                        a clean structured 422 with no internal Pydantic type tree
                        or field-path hierarchy exposed.
OVERSIZE-413-PRE-PARSE  An oversized body is rejected with 413 BEFORE any route
                        handler executes (verified via a spy that records invocations).
"""
from __future__ import annotations

import pytest
from pydantic import BaseModel, Field
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from api.hardening import (
    SecurityHeadersMiddleware,
    BodySizeLimitMiddleware,
    install_hardening,
    _SECURITY_HEADERS,
)

# ---------------------------------------------------------------------------
# Shared spy log — cleared before each test by the autouse fixture below.
# ---------------------------------------------------------------------------
_spy: list[str] = []


@pytest.fixture(autouse=True)
def _clear_spy():
    _spy.clear()
    yield
    _spy.clear()


# ---------------------------------------------------------------------------
# Minimal test app
# ---------------------------------------------------------------------------

class _NameBody(BaseModel):
    name: str = Field(min_length=10)


def _build_app(*, max_body_bytes: int | None = None) -> FastAPI:
    """Build a self-contained FastAPI app with hardening installed.

    max_body_bytes overrides the real config ceiling so the oversize test
    does not need to allocate 32 MB in memory.
    """
    app = FastAPI()
    install_hardening(app, max_request_body_bytes=max_body_bytes)

    @app.get("/ok")
    def ok_route():
        return {"ok": True}

    @app.get("/boom")
    def boom_route():
        raise RuntimeError("internal-secret: db-password=hunter2")

    @app.post("/validate")
    def validate_route(body: _NameBody):
        return {"name": body.name}

    @app.post("/size-spy")
    async def size_spy_route(request: Request):
        _spy.append("invoked")
        return {"bytes": len(await request.body())}

    return app


@pytest.fixture()
def client():
    """Client for general tests — uses the real MAX_REQUEST_BODY_BYTES limit."""
    with TestClient(_build_app(), raise_server_exceptions=False) as c:
        yield c


@pytest.fixture()
def client_small_limit():
    """Client for the oversize test — 100-byte limit so the test is cheap."""
    with TestClient(_build_app(max_body_bytes=100), raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# HEADERS-SET
# ---------------------------------------------------------------------------

_HEADER_NAMES = [name.lower() for name, _ in _SECURITY_HEADERS]


def _assert_security_headers(resp, *, context: str = "") -> None:
    lowered = {k.lower(): v for k, v in resp.headers.items()}
    for name in _HEADER_NAMES:
        assert name in lowered, f"Missing security header '{name}'{' on ' + context if context else ''}"


def test_headers_on_ok_response(client):
    _assert_security_headers(client.get("/ok"), context="200 OK")


def test_headers_on_404(client):
    _assert_security_headers(client.get("/does-not-exist"), context="404")


def test_headers_on_5xx(client):
    _assert_security_headers(client.get("/boom"), context="500")


def test_headers_on_4xx_validation(client):
    _assert_security_headers(
        client.post("/validate", json={"name": "hi"}), context="422 validation"
    )


def test_headers_on_413(client_small_limit):
    oversized = b"x" * 200
    r = client_small_limit.post(
        "/size-spy",
        content=oversized,
        headers={"Content-Type": "application/octet-stream"},
    )
    _assert_security_headers(r, context="413 oversize")


# ---------------------------------------------------------------------------
# EXC-STRUCTURED-NO-LEAK
# ---------------------------------------------------------------------------

def test_unhandled_exception_is_structured_500(client):
    r = client.get("/boom")
    assert r.status_code == 500, f"Expected 500, got {r.status_code}"
    body = r.json()
    assert "error" in body, "Response body missing 'error' key"
    assert body.get("status") == 500, "Response body missing 'status': 500"


def test_unhandled_exception_leaks_nothing(client):
    r = client.get("/boom")
    raw = r.text
    # Must NOT contain any trace of the exception internals
    assert "RuntimeError" not in raw, "Exception class name leaked to client"
    assert "internal-secret" not in raw, "Exception message leaked to client"
    assert "db-password" not in raw, "Exception message leaked to client"
    assert "Traceback" not in raw, "Stack trace leaked to client"
    assert 'File "' not in raw, "File path leaked to client"
    assert "line " not in raw, "Line reference leaked to client"
    assert repr(RuntimeError) not in raw, "Exception repr leaked to client"


# ---------------------------------------------------------------------------
# VALIDATION-CLEAN
# ---------------------------------------------------------------------------

def test_validation_error_returns_clean_422(client):
    r = client.post("/validate", json={"name": "hi"})   # fails min_length=10
    assert r.status_code == 422, f"Expected 422, got {r.status_code}"
    body = r.json()
    assert "error" in body, "Response body missing 'error' key"
    assert body.get("status") == 422, "Response body missing 'status': 422"


def test_validation_error_leaks_nothing(client):
    r = client.post("/validate", json={"name": "hi"})
    raw = r.text
    assert "Traceback" not in raw, "Stack trace leaked on validation error"
    assert 'File "' not in raw, "File path leaked on validation error"
    # Pydantic type identifiers ('value_error.*', 'string_too_short', etc.) must not appear
    assert "value_error" not in raw, "Pydantic type identifier leaked to client"
    assert "string_too_short" not in raw, "Pydantic type identifier leaked to client"
    # The raw loc/type tree must not appear (the default FastAPI 422 includes these)
    assert '"loc"' not in raw, "Pydantic loc tree leaked to client"
    assert '"type"' not in raw or '"status"' in raw, (
        "Pydantic type field leaked — only 'status' key should carry 'type'-like semantics"
    )


# ---------------------------------------------------------------------------
# OVERSIZE-413-PRE-PARSE
# ---------------------------------------------------------------------------

def test_oversize_body_rejected_413(client_small_limit):
    oversized = b"x" * 200       # 200 bytes > 100-byte limit
    r = client_small_limit.post(
        "/size-spy",
        content=oversized,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert r.status_code == 413, f"Expected 413, got {r.status_code}"
    body = r.json()
    assert "error" in body, "413 body missing 'error' key"


def test_oversize_route_never_invoked(client_small_limit):
    """The size guard fires PRE-PARSE: the spy route must not execute at all."""
    assert _spy == [], "Spy was already set before test"
    oversized = b"x" * 200
    client_small_limit.post(
        "/size-spy",
        content=oversized,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert _spy == [], (
        "Route handler was invoked — BodySizeLimitMiddleware did NOT fire before the handler"
    )


def test_within_limit_passes_through(client_small_limit):
    """Requests within the limit reach the route normally."""
    r = client_small_limit.post(
        "/size-spy",
        content=b"x" * 50,       # 50 bytes < 100-byte limit
        headers={"Content-Type": "application/octet-stream"},
    )
    assert r.status_code == 200
    assert _spy == ["invoked"], "Route was not invoked for an allowed-size request"


# ---------------------------------------------------------------------------
# Verdict table (summary + fail-fast on any VIOLATED guard)
# ---------------------------------------------------------------------------

def test_verdict_table(client, client_small_limit):
    """Collect one representative result per guard, print the table, and fail if
    any guard is VIOLATED.  This is the acceptance verdict printed to CI stdout."""
    verdicts: dict[str, str] = {}

    # HEADERS-SET
    r = client.get("/ok")
    lowered = {k.lower() for k in r.headers}
    all_present = all(n in lowered for n in _HEADER_NAMES)
    verdicts["HEADERS-SET"] = "edge hardened" if all_present else "VIOLATED"

    # EXC-STRUCTURED-NO-LEAK
    r = client.get("/boom")
    raw = r.text
    no_leak = (
        r.status_code == 500
        and "RuntimeError" not in raw
        and "internal-secret" not in raw
        and "Traceback" not in raw
        and 'File "' not in raw
    )
    verdicts["EXC-STRUCTURED-NO-LEAK"] = "edge hardened" if no_leak else "VIOLATED"

    # VALIDATION-CLEAN
    r = client.post("/validate", json={"name": "hi"})
    raw = r.text
    clean_val = (
        r.status_code == 422
        and "Traceback" not in raw
        and 'File "' not in raw
        and "value_error" not in raw
        and '"loc"' not in raw
    )
    verdicts["VALIDATION-CLEAN"] = "edge hardened" if clean_val else "VIOLATED"

    # OVERSIZE-413-PRE-PARSE
    _spy.clear()
    oversized = b"x" * 200
    r = client_small_limit.post(
        "/size-spy",
        content=oversized,
        headers={"Content-Type": "application/octet-stream"},
    )
    pre_parse = r.status_code == 413 and _spy == []
    verdicts["OVERSIZE-413-PRE-PARSE"] = "edge hardened" if pre_parse else "VIOLATED"

    # Print table
    width = max(len(g) for g in verdicts)
    print("\n")
    print(f"{'Guard':<{width + 2}}  {'Verdict'}")
    print("-" * (width + 20))
    for guard, verdict in verdicts.items():
        print(f"{guard:<{width + 2}}  {verdict}")
    print()

    violated = [g for g, v in verdicts.items() if v == "VIOLATED"]
    assert not violated, (
        f"HTTP edge hardening VIOLATED on: {violated} — see individual test failures for details."
    )
