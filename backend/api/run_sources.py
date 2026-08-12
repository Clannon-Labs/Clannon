"""Project grounded-search tool records onto safe API source events."""

from __future__ import annotations

import ipaddress
import string
import unicodedata
from urllib.parse import SplitResult, urlsplit


_HEX_DIGITS = frozenset(string.hexdigits)


def _valid_hostname(host: str) -> bool:
    """Accept IP literals or DNS hostnames; reject parser-tolerated junk."""
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass

    candidate = host[:-1] if host.endswith(".") else host
    try:
        ascii_host = candidate.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    if not ascii_host or len(ascii_host) > 253:
        return False
    labels = ascii_host.split(".")
    return all(
        label
        and len(label) <= 63
        and label[0].isalnum()
        and label[-1].isalnum()
        and all(char.isalnum() or char == "-" for char in label)
        for label in labels
    )


def _client_source_url(url: str) -> SplitResult | None:
    """Parse one client-facing source URL, or reject it without rewriting."""
    if any(
        char.isspace() or unicodedata.category(char).startswith("C")
        for char in url
    ):
        return None
    for index, char in enumerate(url):
        if char == "%" and (
            index + 2 >= len(url)
            or url[index + 1] not in _HEX_DIGITS
            or url[index + 2] not in _HEX_DIGITS
        ):
            return None
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        # Access validates numeric syntax and the 0..65535 range.
        parsed.port
    except (ValueError, UnicodeError):
        return None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.netloc.endswith(":")
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or not _valid_hostname(host)
    ):
        return None
    return parsed


def collect_sources(ctx) -> list[dict]:
    """Return de-duplicated grounded-search sources in frontend event shape."""
    seen: set[str] = set()
    sources: list[dict] = []
    all_records = list(ctx.tool_calls)
    for expert in ctx.expert_calls:
        all_records.extend(expert.sub_tool_calls)
    for record in all_records:
        if not record.success or not isinstance(record.result, dict):
            continue
        url_list = record.result.get("sources")
        if not isinstance(url_list, list):
            continue
        for url in url_list:
            if not isinstance(url, str) or not url or url in seen:
                continue
            parsed = _client_source_url(url)
            if parsed is None:
                continue
            seen.add(url)
            host = parsed.hostname or ""
            domain = host[4:] if host.lower().startswith("www.") else host
            path = parsed.path.rstrip("/")
            slug = (
                path.split("/")[-1].replace("-", " ").replace("_", " ").strip()
                if path
                else ""
            )
            title = f"{domain} — {slug}" if slug else domain
            sources.append({
                "id": f"src_{len(sources) + 1}",
                "title": title,
                "url": url,
                "domain": domain,
            })
    return sources
