"""fetch_url tool (key: web.fetch_url) — fetch a page and return its text.

SSRF-guarded: only http/https, no credentials in the URL, and the resolved IP of
every hop (including redirects, which are followed manually) must not be loopback,
link-local, private, reserved, multicast, or unspecified. This blocks the common
SSRF targets (cloud metadata at 169.254.169.254, localhost, RFC1918).

TODO (post-checkpoint): pin the connection to the validated IP to fully close the
DNS-rebinding TOCTOU window between resolve and connect.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel

from foundation import PermissionLevel, constants

from ..registry import tool

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_MAX_REDIRECTS = 5


class FetchBlocked(Exception):
    """Raised when a URL fails SSRF validation."""


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    return _WS.sub(" ", _TAG.sub(" ", html)).strip()


async def _validate(url: str) -> None:
    """Reject non-http(s), credentialed, or internal-resolving URLs."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise FetchBlocked("only http/https URLs are allowed")
    if parts.username or parts.password:
        raise FetchBlocked("URLs with embedded credentials are not allowed")

    host = (parts.hostname or "").strip().rstrip(".").lower()
    if not host:
        raise FetchBlocked("URL has no host")
    port = parts.port or (443 if parts.scheme == "https" else 80)

    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    if not infos:
        raise FetchBlocked(f"could not resolve host {host!r}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_loopback or ip.is_link_local or ip.is_private
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise FetchBlocked(f"blocked internal address for {host!r}: {ip}")


class FetchIn(BaseModel):
    url: str


class FetchOut(BaseModel):
    url: str
    text: str


@tool(
    name="fetch_url",
    domain="web",
    description="Fetch a web page over HTTP(S) and return its readable text.",
    input_schema=FetchIn,
    output_schema=FetchOut,
    permission=PermissionLevel.NETWORK,
    tags=("http", "read"),
)
class FetchUrlTool:
    async def run(self, args: FetchIn) -> FetchOut:
        url = args.url
        async with httpx.AsyncClient(timeout=constants.TOOL_TIMEOUT_S, follow_redirects=False) as client:
            for _ in range(_MAX_REDIRECTS + 1):
                await _validate(url)                      # re-validate every hop
                response = await client.get(url)
                if response.next_request is not None:     # a redirect we must vet
                    url = str(response.next_request.url)
                    continue
                response.raise_for_status()
                text = _html_to_text(response.text)[: constants.TOOL_MAX_OUTPUT_BYTES]
                return FetchOut(url=url, text=text)
        raise FetchBlocked("too many redirects")
