"""
HTTP edge hardening — three additive guards installed via a single install_hardening(app) call.

(1) SecurityHeadersMiddleware   adds X-Content-Type-Options, X-Frame-Options, Referrer-Policy,
    HSTS, and a conservative CSP to EVERY response. Raw ASGI — does NOT buffer streaming
    responses so the SSE pass-through at /runs/{id}/stream is unaffected.

(2) Global exception handler    catches any unhandled exception, logs the full detail
    server-side via the existing clannon.api logger, and returns a generic structured
    {"error": ..., "status": 500} — NEVER exposing a stack trace, file path, or exception
    repr to the client. RequestValidationError is handled separately for a clean 422.

(3) BodySizeLimitMiddleware     rejects a request whose Content-Length (or streamed body)
    exceeds MAX_REQUEST_BODY_BYTES with HTTP 413 BEFORE the body is fully buffered or any
    route/pipeline stage runs. Distinct from and earlier than intake's post-parse char cap —
    this is the transport-layer twin of the size-overload resilience guard.
"""
from __future__ import annotations

import json
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from . import config

_log = logging.getLogger("clannon.api")

# ---------------------------------------------------------------------------
# (1) Security response headers
# ---------------------------------------------------------------------------

# Boilerplate values — the maintainer tunes these as the CSP evolves.
# connect-src 'self' is the minimum needed for the browser to open the SSE stream
# to this same origin.  Do NOT touch the CORS allow-list (managed by config.py / app.py).
_SECURITY_HEADERS: list[tuple[str, str]] = [
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
    ("Strict-Transport-Security", "max-age=63072000; includeSubDomains"),
    ("Content-Security-Policy", "default-src 'self'; connect-src 'self'"),
]


class SecurityHeadersMiddleware:
    """Injects security response headers on every HTTP response. Raw ASGI so that
    StreamingResponse / SSE bodies are never buffered by the middleware layer."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def _send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                headers = MutableHeaders(scope=message)
                for name, value in _SECURITY_HEADERS:
                    headers[name] = value   # setitem deduplicates existing occurrences
            await send(message)

        await self.app(scope, receive, _send_with_headers)


# ---------------------------------------------------------------------------
# (2) Global exception handler — structured JSON, no leak
# ---------------------------------------------------------------------------


def _structured_error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message, "status": status}, status_code=status)


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for any exception that escapes a route. Full detail logged server-side;
    the client receives only a generic message — no exception class, repr, or traceback.

    Security headers are added here explicitly because this handler is dispatched by
    ServerErrorMiddleware (FastAPI routes Exception/500 handlers there, not to
    ExceptionMiddleware). ServerErrorMiddleware sends the response via its own `send`
    parameter — OUTSIDE the SecurityHeadersMiddleware wrapper — so the headers must be
    embedded in the response object itself. See also: needs-reviewer #73.
    """
    _log.exception(
        "Unhandled exception [%s %s]: %s",
        request.method,
        request.url.path,
        type(exc).__name__,
        exc_info=exc,
    )
    response = _structured_error(500, "An unexpected error occurred.")
    for name, value in _SECURITY_HEADERS:
        response.headers[name] = value
    return response


async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Convert Pydantic request-validation failures to a clean structured 422.
    The raw Pydantic loc/type tree is not forwarded — only human-readable messages."""
    errors = exc.errors()
    if errors:
        msgs = [e.get("msg", "invalid value") for e in errors[:3]]
        detail = "; ".join(msgs)
    else:
        detail = "Invalid request."
    return _structured_error(422, detail)


# ---------------------------------------------------------------------------
# (3) Pre-parse body-size guard
# ---------------------------------------------------------------------------


class _BodyTooLarge(Exception):
    pass


async def _send_413(send: Send) -> None:
    body = json.dumps({"error": "Request body too large.", "status": 413}).encode()
    await send({
        "type": "http.response.start",
        "status": 413,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
    })
    await send({"type": "http.response.body", "body": body, "more_body": False})


class BodySizeLimitMiddleware:
    """Rejects oversized requests with HTTP 413 BEFORE the body is buffered or any
    route/pipeline stage runs.

    Two enforcement paths:
      (a) Content-Length present — rejected immediately from the header alone.
      (b) Chunked / streaming — bytes are counted as they arrive in the receive
          wrapper; the first chunk that tips the total over the limit aborts.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # (a) Content-Length fast path
        req_headers = Headers(scope=scope)
        raw_cl = req_headers.get("content-length")
        if raw_cl is not None:
            try:
                if int(raw_cl) > self.max_bytes:
                    await _send_413(send)
                    return
            except (ValueError, TypeError):
                pass  # malformed Content-Length — framework handles it

        # (b) Streaming path: accumulate byte count across receive calls
        received = 0

        async def _limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLarge()
            return message

        try:
            await self.app(scope, _limited_receive, send)
        except _BodyTooLarge:
            await _send_413(send)


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def install_hardening(
    app: FastAPI,
    *,
    max_request_body_bytes: int | None = None,
) -> None:
    """Wire all three HTTP edge guards into *app*. Call once, immediately after the
    CORSMiddleware registration in api/app.py.

    Middleware stack after this call (outermost -> innermost):
        SecurityHeadersMiddleware      <- outermost user middleware; headers on ALL responses
        BodySizeLimitMiddleware        <- rejects oversized bodies before routes or CORS
        [CORSMiddleware]               <- already registered by api/app.py
        ExceptionMiddleware            <- holds our structured-error handlers
        Routes
    """
    limit = (
        max_request_body_bytes
        if max_request_body_bytes is not None
        else getattr(config, "MAX_REQUEST_BODY_BYTES", 32 * 1024 * 1024)
    )

    # Exception handler routing: Starlette's build_middleware_stack() separates
    # Exception (and 500) handlers from the rest and passes them to ServerErrorMiddleware
    # as its `handler`, NOT to ExceptionMiddleware. ServerErrorMiddleware sends that
    # handler's response via its own send path, bypassing SecurityHeadersMiddleware.
    # _unhandled_exception_handler therefore embeds the security headers in the response
    # object itself. See the docstring there. (needs-reviewer #73 documents this wall.)
    #
    # RequestValidationError is NOT Exception/500, so it goes to ExceptionMiddleware —
    # its response DOES flow through SecurityHeadersMiddleware (headers added by the
    # middleware, not by the handler).
    #
    # StarletteHTTPException is NOT overridden: FastAPI's default handler returns
    # {"detail": "..."} which the frontend reads verbatim (api/CLAUDE.md), and all
    # raise HTTPException(...) calls produce clean strings — no internal leak.
    app.add_exception_handler(Exception, _unhandled_exception_handler)          # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)

    # BodySizeLimitMiddleware first, so SecurityHeaders wraps it (413 gets headers too).
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=limit)

    # SecurityHeadersMiddleware last = outermost user middleware.
    app.add_middleware(SecurityHeadersMiddleware)
