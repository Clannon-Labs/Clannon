"""http_request tool (key: http.request) — make ONE outbound HTTP request to an
external service: POST a payload to a webhook (Slack/Discord/Zapier/custom) or call
a REST API, and return the status + response.

SSRF-guarded by the shared `tools._net.validate_public_url`: only http/https, no
embedded credentials, and the URL must not resolve to an internal address (loopback,
RFC1918, link-local, cloud metadata). Redirects are NOT followed — a webhook that
3xx-redirects just returns that status. NETWORK permission, so the handler
re-sanitizes the (untrusted) response before it can reach reasoning.

NOTE (security): this is an OUTBOUND data path — anything sent leaves the system.
The destination comes from the run's request; a first-cut mitigation is the SSRF gate
+ NETWORK auditing. A per-user destination allowlist / send-confirmation is a planned
hardening before this is exposed to untrusted multi-tenant traffic.
"""

from __future__ import annotations

from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

import settings
from foundation import PermissionLevel

from registry import tool

from ._net import decode_response, read_capped, validate_public_url


class HttpIn(BaseModel):
    url: str = Field(
        description="The external http(s) URL to call (a webhook endpoint or REST API). "
        "Internal / loopback / metadata addresses are blocked."
    )
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = Field(
        default="POST", description="HTTP method. POST to deliver to a webhook."
    )
    json_body: dict[str, Any] | None = Field(
        default=None,
        description="JSON payload to send as the body (POST/PUT/PATCH). Shape it for the "
        'destination, e.g. {"text": "..."} for a Slack incoming webhook.',
    )
    headers: dict[str, str] | None = Field(
        default=None, description="Optional request headers (e.g. Content-Type, Authorization)."
    )


class HttpOut(BaseModel):
    status: int                # the HTTP status code returned
    ok: bool                   # True for a 2xx response
    body: str                  # response text, capped


@tool
class HttpRequestTool:
    name = "request"
    domain = "http"
    description = (
        "Make an outbound HTTP request to an external URL (POST a payload to a webhook, or "
        "call a REST API) and return the status + response. SSRF-guarded: internal addresses "
        "are blocked. Use to DELIVER a result to a channel or to call an external service."
    )
    input_schema = HttpIn
    output_schema = HttpOut
    permission = PermissionLevel.NETWORK
    tags = ("http", "webhook", "deliver", "api")

    async def run(self, args: HttpIn) -> HttpOut:
        await validate_public_url(args.url)
        headers = dict(list((args.headers or {}).items())[:settings.TOOLS.http_request_max_headers]) or None
        async with httpx.AsyncClient(timeout=settings.TOOLS.timeout_s, follow_redirects=False) as client:
            # stream + cap: a hostile endpoint can't flood memory with a huge response
            async with client.stream(args.method, args.url, json=args.json_body, headers=headers) as response:
                raw = await read_capped(response, settings.TOOLS.fetch_max_response_bytes)
            body = decode_response(raw, response)[: settings.TOOLS.max_output_bytes]
        return HttpOut(status=response.status_code, ok=response.is_success, body=body)
