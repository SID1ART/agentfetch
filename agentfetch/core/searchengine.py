import asyncio
import logging
import os
import random
from dataclasses import dataclass, field
from typing import Optional, AsyncIterator
from urllib.parse import quote

import httpx

from .schema import FetchResult, SearchResult, ScrapeConfig
from .router import smart_fetch
from .proxymanager import ProxyManager

logger = logging.getLogger("agentfetch.searchengine")

SEARXNG_URL = os.environ.get("SEARXNG_URL", "")
BRAVE_SEARCH_API_KEY = os.environ.get("BRAVE_SEARCH_API_KEY", "")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GOOGLE_CX = os.environ.get("GOOGLE_CX", "")

SEARCH_RETRIES = int(os.environ.get("AGENTFETCH_SEARCH_RETRIES", "2"))
SEARCH_TIMEOUT = int(os.environ.get("AGENTFETCH_SEARCH_TIMEOUT", "15"))

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

CATEGORY_QUERY_MODIFIERS = {
    "company": "company OR startup OR headquarters OR funding",
    "news": "latest OR today OR breaking",
    "people": "LinkedIn OR profile OR bio OR founder",
    "research_paper": "paper OR arXiv OR research OR study",
    "personal_site": "blog OR personal site OR portfolio",
}


def generate_query_variations(query: str) -> list[str]:
    variations = [query]
    words = query.split()
    if len(words) >= 3:
        variations.append(" ".join(words[:-1]))
    if len(words) >= 2:
        variations.append(f"{query} overview")
        variations.append(f"{query} guide")
    return variations[:4]


_search_proxy_manager: Optional[ProxyManager] = None


def _get_search_proxy() -> Optional[str]:
    global _search_proxy_manager
    if _search_proxy_manager is None:
        _search_proxy_manager = ProxyManager()
    if _search_proxy_manager.is_enabled():
        try:
            return asyncio.run(_search_proxy_manager.get_proxy())
        except RuntimeError:
            return None
    return None


def _is_rate_limited(error: str) -> bool:
    lower = error.lower()
    patterns = ["429", "rate limit", "too many requests", "quota exceeded"]
    return any(p in lower for p in patterns)


async def _with_search_retry(fn, *args, **kwargs) -> list["EngineResult"]:
    last_err = ""
    for attempt in range(1 + SEARCH_RETRIES):
        try:
            return await fn(*args, **kwargs)
        except Exception as e:
            last_err = str(e)
            if _is_rate_limited(last_err) and attempt < SEARCH_RETRIES:
                wait = (2**attempt) + random.uniform(0, 1)
                logger.info(
                    "Search rate limited, retry %d/%d after %.1fs",
                    attempt + 1,
                    SEARCH_RETRIES,
                    wait,
                )
                await asyncio.sleep(wait)
                continue
            raise
    msg = f"all {SEARCH_RETRIES + 1} attempts failed: {last_err}"
    raise RuntimeError(msg)


def _configure_searxng(url: str):
    global SEARXNG_URL
    SEARXNG_URL = url


@dataclass
class EngineResult:
    title: str
    url: str
    snippet: str
    source: str


def _search_client(**kwargs) -> httpx.AsyncClient:
    proxy = _get_search_proxy()
    merged = {"timeout": SEARCH_TIMEOUT}
    if proxy:
        merged["proxies"] = proxy
    merged.update(kwargs)
    return httpx.AsyncClient(**merged)


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
        if _is_rate_limited(str(e)):
            raise
        logger.warning("DuckDuckGo search failed: %s", e)
        return []


async def _search_brave_api(query: str, max_results: int) -> list[EngineResult]:
    if not BRAVE_SEARCH_API_KEY:
        return []
    try:
        url = "https://api.search.brave.com/res/v1/web/search"
        headers = {
            "X-Subscription-Token": BRAVE_SEARCH_API_KEY,
            "Accept": "application/json",
        }
        params = {"q": query, "count": min(max_results, 20)}
        async with _search_client() as client:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
        results = []
        for item in data.get("web", {}).get("results", [])[:max_results]:
            results.append(
                EngineResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("description", ""),
                    source="brave",
                )
            )
        return results
    except Exception as e:
        if _is_rate_limited(str(e)):
            raise
        logger.warning("Brave Search API failed: %s", e)
        return []


async def _search_serpapi(query: str, max_results: int) -> list[EngineResult]:
    if not SERPAPI_KEY:
        return []
    try:
        url = "https://serpapi.com/search"
        params = {
            "q": query,
            "api_key": SERPAPI_KEY,
            "engine": "google",
            "num": min(max_results, 10),
        }
        async with _search_client() as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        results = []
        for item in data.get("organic_results", [])[:max_results]:
            results.append(
                EngineResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                    source="serpapi",
                )
            )
        return results
    except Exception as e:
        if _is_rate_limited(str(e)):
            raise
        logger.warning("SerpAPI search failed: %s", e)
        return []


async def _search_google_api(query: str, max_results: int) -> list[EngineResult]:
    if not GOOGLE_API_KEY or not GOOGLE_CX:
        return []
    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "q": query,
            "key": GOOGLE_API_KEY,
            "cx": GOOGLE_CX,
            "num": min(max_results, 10),
        }
        async with _search_client() as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        results = []
        for item in data.get("items", [])[:max_results]:
            results.append(
                EngineResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                    source="google_api",
                )
            )
        return results
    except Exception as e:
        if _is_rate_limited(str(e)):
            raise
        logger.warning("Google Custom Search API failed: %s", e)
        return []


async def _search_google(query: str, max_results: int) -> list[EngineResult]:
    if GOOGLE_API_KEY and GOOGLE_CX:
        api_results = await _search_google_api(query, max_results)
        if api_results:
            return api_results
        logger.info("Google API returned no results, falling back to scraping")
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
        msg = str(e)
        if _is_rate_limited(msg):
            raise
        logger.warning("Google search failed: %s", msg)
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
        async with _search_client(headers=headers, follow_redirects=True) as client:
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
        if _is_rate_limited(str(e)):
            raise
        logger.warning("Bing search failed: %s", e)
        return []


async def _search_searxng(
    query: str, max_results: int, searxng_url: str = ""
) -> list[EngineResult]:
    base_url = searxng_url or SEARXNG_URL
    if not base_url:
        return []

    try:
        async with _search_client() as client:
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
        if _is_rate_limited(str(e)):
            raise
        logger.warning("SearXNG search failed: %s", e)
        return []


ENGINE_NAMES = ["duckduckgo", "google", "bing", "searxng", "brave", "serpapi"]

ENGINE_REGISTRY: dict[str, callable] = {
    "duckduckgo": _search_ddg,
    "google": _search_google,
    "bing": _search_bing,
    "searxng": _search_searxng,
    "brave": _search_brave_api,
    "serpapi": _search_serpapi,
}

_ENGINE_FN_MAP: dict[str, str] = {
    "duckduckgo": "_search_ddg",
    "google": "_search_google",
    "bing": "_search_bing",
    "searxng": "_search_searxng",
    "brave": "_search_brave_api",
    "serpapi": "_search_serpapi",
}


def _get_engine_fn(name: str) -> callable:
    import sys

    attr = _ENGINE_FN_MAP.get(name)
    if attr:
        mod = sys.modules[__name__]
        if hasattr(mod, attr):
            return getattr(mod, attr)
    return ENGINE_REGISTRY.get(name, _search_ddg)


def _resolve_sources(sources: Optional[list[str]], searxng_url: str) -> list[str]:
    if sources is not None:
        return [s for s in sources if s in ENGINE_REGISTRY] or ["duckduckgo"]
    resolved = []
    if BRAVE_SEARCH_API_KEY:
        resolved.append("brave")
    else:
        resolved.append("duckduckgo")
    if SERPAPI_KEY:
        resolved.append("serpapi")
    else:
        resolved.append("google")
    resolved.append("bing")
    if searxng_url or SEARXNG_URL:
        resolved.append("searxng")
    return resolved


async def parallel_search(
    query: str,
    sources: Optional[list[str]] = None,
    max_results: int = 5,
    searxng_url: str = "",
    depth: str = "auto",
    category: str = "auto",
) -> tuple[list[EngineResult], list[str], dict[str, str]]:
    valid_sources = _resolve_sources(sources, searxng_url)

    if category != "auto" and category in CATEGORY_QUERY_MODIFIERS:
        modifier = CATEGORY_QUERY_MODIFIERS[category]
        query = f"({query}) {modifier}"

    queries_to_run = [query]
    if depth == "deep":
        queries_to_run = generate_query_variations(query)

    seen_urls: dict[str, str] = {}
    merged: list[EngineResult] = []
    engines_used: set[str] = set()
    engine_errors: dict[str, str] = {}

    for q in queries_to_run:

        async def _run_with_retry(src: str) -> list[EngineResult]:
            fn = _get_engine_fn(src)
            if src == "searxng":
                return await _with_search_retry(fn, q, max_results, searxng_url)
            return await _with_search_retry(fn, q, max_results)

        tasks = [_run_with_retry(src) for src in valid_sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, src_results in enumerate(results):
            src_name = valid_sources[i]
            if isinstance(src_results, Exception):
                engine_errors[src_name] = str(src_results)
                logger.warning("Engine %s failed: %s", src_name, src_results)
                continue
            engines_used.add(src_name)
            if not src_results:
                engine_errors[src_name] = "returned zero results"
            for r in src_results:
                dedup_key = r.url.rstrip("/").lower()
                if dedup_key not in seen_urls:
                    seen_urls[dedup_key] = r.url
                    merged.append(r)

    return merged[:max_results], sorted(engines_used), engine_errors


async def stream_search(
    query: str,
    sources: Optional[list[str]] = None,
    max_results: int = 5,
    searxng_url: str = "",
) -> AsyncIterator[EngineResult]:
    valid_sources = _resolve_sources(sources, searxng_url)

    async def _run_one(src: str) -> list[EngineResult]:
        fn = _get_engine_fn(src)
        if src == "searxng":
            return await _with_search_retry(fn, query, max_results, searxng_url)
        return await _with_search_retry(fn, query, max_results)

    cores = [_run_one(src) for src in valid_sources]
    seen: set[str] = set()
    for coro in asyncio.as_completed(cores):
        try:
            results = await coro
        except Exception:
            continue
        for r in results:
            key = r.url.rstrip("/").lower()
            if key not in seen:
                seen.add(key)
                yield r


async def search_fetch(
    query: str,
    sources: Optional[list[str]] = None,
    max_results: int = 5,
    scrape_results: bool = True,
    searxng_url: str = "",
    config: Optional[ScrapeConfig] = None,
    category: str = "auto",
    depth: str = "auto",
) -> SearchResult:
    config = config or ScrapeConfig()
    if category != "auto":
        config.category = category

    results, engines_used, engine_errors = await parallel_search(
        query=query,
        sources=sources,
        max_results=max_results,
        searxng_url=searxng_url,
        depth=depth,
        category=category,
    )

    fetch_results: list[FetchResult] = []
    if scrape_results:
        fetch_tasks = []
        for r in results:
            cfg = config.model_copy()
            category_hint = category
            if _guess_category_from_snippet(r.snippet, r.url) != "unknown":
                category_hint = _guess_category_from_snippet(r.snippet, r.url)
            if category_hint != "auto":
                cfg.category = category_hint
            fetch_tasks.append(smart_fetch(r.url, config=cfg))
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
        errors=engine_errors,
        total_results=len(results),
    )


def _guess_category_from_snippet(snippet: str, url: str) -> str:
    lower = (snippet + " " + url).lower()
    if any(
        d in url.lower() for d in ("arxiv.org", "openreview.net", "research", "paper")
    ):
        return "research_paper"
    if any(d in url.lower() for d in ("linkedin.com", "crunchbase.com")):
        return "people"
    if any(d in url.lower() for d in ("blog.", "/blog/", "medium.com")):
        return "personal_site"
    if any(d in url.lower() for d in ("techcrunch", "wired", "reuters", "news")):
        return "news"
    if any(d in url.lower() for d in ("company", "startup", "about", "crunchbase")):
        return "company"
    return "unknown"
