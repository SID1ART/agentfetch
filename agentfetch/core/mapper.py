import asyncio
import logging
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx

from .schema import MapConfig, MapResult

logger = logging.getLogger("agentfetch.mapper")


async def _fetch_sitemap(url: str) -> list[str]:
    base = url.rstrip("/")
    sitemap_urls = [
        f"{base}/sitemap.xml",
        f"{base}/sitemap_index.xml",
        f"{base}/sitemap/sitemap.xml",
    ]

    parsed = urlparse(url)
    if parsed.path:
        dir_part = parsed.path.rsplit("/", 1)[0] if "/" in parsed.path else ""
        if dir_part:
            sitemap_urls.append(f"{parsed.scheme}://{parsed.netloc}{dir_part}/sitemap.xml")

    links: set[str] = set()
    for sm_url in sitemap_urls:
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(sm_url)
                if resp.status_code != 200:
                    continue
                content = resp.text
                if "<urlset" in content or "<sitemapindex" in content or "<url>" in content:
                    import xml.etree.ElementTree as ET

                    root = ET.fromstring(content)
                    ns = re.sub(r"\{.*?\}", "", root.tag[: root.tag.index("}") + 1]) if "}" in root.tag else ""
                    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
                    for loc in root.iterfind(".//sm:loc", ns) if ns else root.iter():
                        tag = loc.text.strip() if loc.text else ""
                        if tag:
                            links.add(tag)
                    if links:
                        logger.info("Found %d URLs in sitemap: %s", len(links), sm_url)
                        break
        except Exception:
            continue
    return list(links)


async def _bfs_discover(base_url: str, config: MapConfig) -> list[str]:
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(base_url, 0)]
    discovered: set[str] = set()
    domain = urlparse(base_url).netloc

    while queue and len(discovered) < config.max_pages:
        url, depth = queue.pop(0)
        if url in visited or depth > config.max_depth:
            continue
        visited.add(url)

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    continue
                from bs4 import BeautifulSoup

                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    full = urljoin(url, a["href"])
                    if not full.startswith("http"):
                        continue
                    parsed = urlparse(full)
                    if parsed.fragment:
                        full = full.replace(f"#{parsed.fragment}", "")
                    if config.include_domains:
                        if not any(d in parsed.netloc for d in config.include_domains):
                            continue
                    if config.exclude_domains:
                        if any(d in parsed.netloc for d in config.exclude_domains):
                            continue
                    if config.include_patterns:
                        if not any(re.search(p, parsed.path) for p in config.include_patterns):
                            continue
                    if config.exclude_patterns:
                        if any(re.search(p, parsed.path) for p in config.exclude_patterns):
                            continue
                    if full not in visited:
                        discovered.add(full)
                        if len(discovered) < config.max_pages and depth < config.max_depth:
                            if parsed.netloc == domain or config.include_domains:
                                queue.append((full, depth + 1))
        except Exception:
            continue

    return list(discovered)


def _filter_urls(urls: list[str], config: MapConfig) -> list[str]:
    result = set()
    for url in urls:
        parsed = urlparse(url)
        if config.include_domains:
            if not any(d in parsed.netloc for d in config.include_domains):
                continue
        if config.exclude_domains:
            if any(d in parsed.netloc for d in config.exclude_domains):
                continue
        if config.include_patterns:
            if not any(re.search(p, parsed.path) for p in config.include_patterns):
                continue
        if config.exclude_patterns:
            if any(re.search(p, parsed.path) for p in config.exclude_patterns):
                continue
        result.add(url)
    return list(result)


async def smart_map(
    url: str,
    config: Optional[MapConfig] = None,
) -> MapResult:
    config = config or MapConfig()
    links: set[str] = set()
    sources: list[str] = []

    sitemap_links = await _fetch_sitemap(url)
    if sitemap_links:
        links.update(sitemap_links)
        sources.append("sitemap")
        if len(links) >= config.max_pages:
            filtered = _filter_urls(list(links), config)
            return MapResult(
                base_url=url,
                links=filtered[: config.max_pages],
                total=len(filtered),
                sources=sources,
            )

    crawl_links = await _bfs_discover(url, config)
    if crawl_links:
        links.update(crawl_links)
        sources.append("crawl")

    filtered = _filter_urls(list(links), config)
    return MapResult(
        base_url=url,
        links=filtered[: config.max_pages],
        total=len(filtered),
        sources=sources,
    )
