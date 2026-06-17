import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote

import httpx

from .schema import FetchResult, SearchResult, ScrapeConfig
from .router import smart_fetch

logger = logging.getLogger("agentfetch.searchengine")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

SEARXNG_URL = ""


def _configure_searxng(url: str):
    global SEARXNG_URL
    SEARXNG_URL = url


@dataclass
class EngineResult:
    title: str
    url: str
    snippet: str
    source: str


async def _search_ddg(query: str, max_results: int) -> list[EngineResult]:
    try:
        from duckduckgo_search import DDGS

        loop = asyncio.get_event_loop()

        def _fetch():
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))

        results = await loop.run_in_executor(None, _fetch)
        return [
            EngineResult(
                title=r.get("title", ""),
                url=r.get("href", ""),
                snippet=r.get("body", ""),
                source="duckduckgo",
            )
            for r in results
            if r.get("href")
        ]
    except Exception as e:
        logger.warning("DuckDuckGo search failed: %s", e)
        return []


async def _search_google(query: str, max_results: int) -> list[EngineResult]:
    try:
        from googlesearch import search

        loop = asyncio.get_event_loop()

        def _fetch():
            try:
                return list(search(query, num_results=max_results, lang="en"))
            except TypeError:
                return list(search(query, stop=max_results, lang="en"))

        results = await loop.run_in_executor(None, _fetch)
        return [
            EngineResult(
                title="",
                url=r if isinstance(r, str) else getattr(r, "url", str(r)),
                snippet="",
                source="google",
            )
            for r in results
            if r
        ]
    except ImportError:
        logger.debug("googlesearch-python not installed, skipping Google search")
        return []
    except Exception as e:
        logger.warning("Google search failed: %s", e)
        return []


async def _search_bing(query: str, max_results: int) -> list[EngineResult]:
    try:
        from bs4 import BeautifulSoup

        url = f"https://www.bing.com/search?q={quote(query)}&count={max_results}"
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with httpx.AsyncClient(
            headers=headers, timeout=15.0, follow_redirects=True
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for li in soup.select("li.b_algo"):
            h2 = li.select_one("h2")
            a = h2.select_one("a") if h2 else None
            p = li.select_one("p")
            if a and a.get("href"):
                results.append(
                    EngineResult(
                        title=a.get_text(strip=True),
                        url=a["href"],
                        snippet=p.get_text(strip=True) if p else "",
                        source="bing",
                    )
                )
        return results[:max_results]
    except Exception as e:
        logger.warning("Bing search failed: %s", e)
        return []


async def _search_searxng(
    query: str, max_results: int, searxng_url: str = ""
) -> list[EngineResult]:
    base_url = searxng_url or SEARXNG_URL
    if not base_url:
        return []

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{base_url}/search",
                json={"q": query, "format": "json"},
            )
            data = resp.json()
            return [
                EngineResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", ""),
                    source="searxng",
                )
                for item in data.get("results", [])[:max_results]
                if item.get("url")
            ]
    except Exception as e:
        logger.warning("SearXNG search failed: %s", e)
        return []


ENGINE_NAMES = ["duckduckgo", "google", "bing", "searxng"]

ENGINE_REGISTRY: dict[str, callable] = {
    "duckduckgo": _search_ddg,
    "google": _search_google,
    "bing": _search_bing,
    "searxng": _search_searxng,
}


def _get_engine_fn(name: str) -> callable:
    import sys

    mod = sys.modules[__name__]
    attr = f"_search_{name}"
    if hasattr(mod, attr):
        return getattr(mod, attr)
    return ENGINE_REGISTRY.get(name, _search_ddg)


async def parallel_search(
    query: str,
    sources: Optional[list[str]] = None,
    max_results: int = 5,
    searxng_url: str = "",
) -> tuple[list[EngineResult], list[str]]:
    if sources is None:
        sources = ["duckduckgo", "google", "bing"]
        if searxng_url or SEARXNG_URL:
            sources.append("searxng")

    valid_sources = [s for s in sources if s in ENGINE_REGISTRY]
    if not valid_sources:
        valid_sources = ["duckduckgo"]
        sources = ["duckduckgo"]

    tasks = []
    for src in valid_sources:
        fn = _get_engine_fn(src)
        if src == "searxng":
            tasks.append(fn(query, max_results, searxng_url))
        else:
            tasks.append(fn(query, max_results))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    seen_urls: dict[str, str] = {}
    merged: list[EngineResult] = []
    engines_used: set[str] = set()

    for i, src_results in enumerate(results):
        src_name = valid_sources[i]
        if isinstance(src_results, Exception):
            logger.warning("Engine %s raised exception: %s", src_name, src_results)
            continue
        engines_used.add(src_name)
        for r in src_results:
            dedup_key = r.url.rstrip("/").lower()
            if dedup_key not in seen_urls:
                seen_urls[dedup_key] = r.url
                merged.append(r)

    return merged[:max_results], sorted(engines_used)


async def search_fetch(
    query: str,
    sources: Optional[list[str]] = None,
    max_results: int = 5,
    scrape_results: bool = True,
    searxng_url: str = "",
    config: Optional[ScrapeConfig] = None,
) -> SearchResult:
    results, engines_used = await parallel_search(
        query=query,
        sources=sources,
        max_results=max_results,
        searxng_url=searxng_url,
    )

    fetch_results: list[FetchResult] = []
    if scrape_results:
        fetch_tasks = []
        for r in results:
            fetch_tasks.append(smart_fetch(r.url, config=config))
        fetched = await asyncio.gather(*fetch_tasks, return_exceptions=True)
        for i, fr in enumerate(fetched):
            if isinstance(fr, FetchResult):
                fr.title = fr.title or results[i].title
                fetch_results.append(fr)
            else:
                r = results[i]
                fetch_results.append(
                    FetchResult(
                        url=r.url,
                        content=r.snippet,
                        title=r.title,
                        confidence=0.3,
                        render_mode="static",
                        error=str(fr) if isinstance(fr, Exception) else None,
                    )
                )
    else:
        for r in results:
            fetch_results.append(
                FetchResult(
                    url=r.url,
                    content=r.snippet,
                    title=r.title,
                    confidence=0.5,
                    render_mode="static",
                )
            )

    source_label = "+".join(engines_used) if engines_used else "none"
    return SearchResult(
        query=query,
        results=fetch_results,
        source=source_label,
        sources_used=engines_used,
        total_results=len(results),
    )
