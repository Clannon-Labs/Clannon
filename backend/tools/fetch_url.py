"""fetch_url tool (key: web.fetch_url) — fetch a page and return its text.

SSRF-guarded via the shared `tools._net.validate_public_url` (the single SSRF gate
for every network tool): only http/https, no credentials in the URL, and the
resolved IP of every hop (including redirects, which are followed manually) must
not be internal. This blocks the common SSRF targets (cloud metadata at
169.254.169.254, localhost, RFC1918).
"""

from __future__ import annotations

import re

import httpx
from pydantic import BaseModel

from foundation import PermissionLevel, constants

from registry import tool

from ._net import UnsafeUrlError, decode_response, read_capped, validate_public_url

# back-compat aliases: the response cap reuses the shared exception + reader
FetchBlocked = UnsafeUrlError
_read_capped = read_capped

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_MAX_REDIRECTS = 5


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    return _WS.sub(" ", _TAG.sub(" ", html)).strip()


class FetchIn(BaseModel):
    url: str


class FetchOut(BaseModel):
    url: str
    text: str


@tool
class FetchUrlTool:
    name = "fetch_url"
    domain = "web"
    description = "Fetch a web page over HTTP(S) and return its readable text."
    input_schema = FetchIn
    output_schema = FetchOut
    permission = PermissionLevel.NETWORK
    tags = ("http", "read")

    async def run(self, args: FetchIn) -> FetchOut:
        url = args.url
        async with httpx.AsyncClient(timeout=constants.TOOL_TIMEOUT_S, follow_redirects=False) as client:
            for _ in range(_MAX_REDIRECTS + 1):
                await validate_public_url(url)            # re-validate every hop
                # stream, never buffer: a server can advertise a small body and
                # then send gigabytes, or omit Content-Length entirely — the cap
                # is enforced on bytes actually received, not on a trusted header
                async with client.stream("GET", url) as response:
                    if response.next_request is not None:  # a redirect we must vet
                        url = str(response.next_request.url)
                        continue
                    response.raise_for_status()
                    raw = await read_capped(response, constants.FETCH_MAX_RESPONSE_BYTES)
                text = _html_to_text(decode_response(raw, response))[: constants.TOOL_MAX_OUTPUT_BYTES]
                return FetchOut(url=url, text=text)
        raise FetchBlocked("too many redirects")
