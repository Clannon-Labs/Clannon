"""
Shared network primitives for the HTTP tools (fetch + outbound request).

The SSRF guard lives HERE, once: every network tool validates its URL through
`validate_public_url` so the rule (no non-http(s), no embedded credentials, no
host that resolves to an internal address) can never drift between two copies.
`read_capped` + `decode_response` are the shared "read a body without trusting its
size, then decode it without executing it" helpers.

TODO (post-checkpoint): pin the connection to the validated IP to close the
DNS-rebinding TOCTOU window between resolve and connect.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

import httpx


class UnsafeUrlError(Exception):
    """Raised when a URL fails SSRF validation or a response exceeds its cap."""


async def validate_public_url(url: str) -> None:
    """Reject non-http(s), credentialed, or internal-resolving URLs — the SSRF gate.

    Blocks the common SSRF targets: cloud metadata (169.254.169.254), localhost,
    RFC1918, and every other loopback/link-local/private/reserved/multicast/
    unspecified address the host resolves to. Call this on EVERY URL and every
    redirect hop, before the request is made."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise UnsafeUrlError("only http/https URLs are allowed")
    if parts.username or parts.password:
        raise UnsafeUrlError("URLs with embedded credentials are not allowed")

    host = (parts.hostname or "").strip().rstrip(".").lower()
    if not host:
        raise UnsafeUrlError("URL has no host")
    port = parts.port or (443 if parts.scheme == "https" else 80)

    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    if not infos:
        raise UnsafeUrlError(f"could not resolve host {host!r}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_loopback or ip.is_link_local or ip.is_private
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise UnsafeUrlError(f"blocked internal address for {host!r}: {ip}")


async def read_capped(response: httpx.Response, limit: int) -> bytes:
    """Read a streamed body, aborting the moment it exceeds `limit` bytes.

    The byte budget is enforced on data actually received — a lying or absent
    Content-Length cannot get past it, and we stop pulling from the socket instead
    of buffering an unbounded body into memory."""
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > limit:
            raise UnsafeUrlError(f"response exceeded {limit} byte cap")
        chunks.append(chunk)
    return b"".join(chunks)


def decode_response(raw: bytes, response: httpx.Response) -> str:
    """Decode bytes using the response charset, never executing the content."""
    encoding = response.charset_encoding or "utf-8"
    try:
        return raw.decode(encoding, errors="replace")
    except (LookupError, TypeError):
        return raw.decode("utf-8", errors="replace")
