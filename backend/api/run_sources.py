"""Project grounded-search tool records onto API source events."""

from urllib.parse import urlparse


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
            seen.add(url)
            try:
                parsed = urlparse(url)
                netloc = parsed.netloc or ""
                domain = netloc[4:] if netloc.startswith("www.") else netloc
                path = parsed.path.rstrip("/")
                slug = path.split("/")[-1].replace("-", " ").replace("_", " ").strip() if path else ""
                title = f"{domain} — {slug}" if slug else domain
            except Exception:  # noqa: BLE001
                domain = ""
                title = url
            sources.append({
                "id": f"src_{len(sources) + 1}",
                "title": title or url,
                "url": url,
                "domain": domain,
            })
    return sources
