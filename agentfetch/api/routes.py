import hashlib
import json
import logging
import os
import time
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from ..core.router import smart_fetch, batch_fetch
from ..core.sanitizer import sanitize
from ..core.schema import FetchResult, CrawlResult, SearchResult
from ..core.stopper import CrawlStopper

logger = logging.getLogger("agentfetch.api.routes")
router = APIRouter()

REDIS_URL = os.environ.get("REDIS_URL", "")
SEARXNG_URL = os.environ.get("SEARXNG_URL", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CACHE_TTL = int(os.environ.get("AGENTFETCH_CACHE_TTL", "3600"))

redis_client = None
if REDIS_URL:
    try:
        import redis as redis_lib

        redis_client = redis_lib.from_url(REDIS_URL)
    except Exception as e:
        logger.warning("Redis not available: %s", e)

_crawl_jobs: dict[str, CrawlResult] = {}


class ScrapeRequest(BaseModel):
    url: str
    engine: str = "auto"
    use_cache: bool = True


class BatchRequest(BaseModel):
    urls: list[str]
    engine: str = "auto"
    concurrency: int = 5


class CrawlRequest(BaseModel):
    url: str
    max_depth: int = 3
    max_pages: int = 20
    query: Optional[str] = None
    strategy: str = "bfs"


class SearchRequest(BaseModel):
    query: str
    max_results: int = 5
    scrape_results: bool = True


class ExtractRequest(BaseModel):
    url: str
    schema: dict


def _cache_key(url: str) -> str:
    return "agentfetch:" + hashlib.sha256(url.encode()).hexdigest()


def _get_cached(url: str) -> Optional[FetchResult]:
    if not redis_client:
        return None
    try:
        data = redis_client.get(_cache_key(url))
        if data:
            return FetchResult.model_validate_json(data)
    except Exception:
        pass
    return None


def _set_cache(url: str, result: FetchResult):
    if not redis_client:
        return
    try:
        redis_client.setex(_cache_key(url), CACHE_TTL, result.model_dump_json())
    except Exception:
        pass


@router.post("/agent_scrape")
async def agent_scrape(req: ScrapeRequest) -> FetchResult:
    if req.use_cache:
        cached = _get_cached(req.url)
        if cached:
            cached.cached = True
            return cached

    result = await smart_fetch(req.url, engine=req.engine)
    _set_cache(req.url, result)
    return result


@router.post("/agent_batch")
async def agent_batch(req: BatchRequest) -> list[FetchResult]:
    results = await batch_fetch(req.urls, concurrency=req.concurrency)
    for r in results:
        _set_cache(r.url, r)
    return results


@router.post("/agent_crawl")
async def agent_crawl(
    req: CrawlRequest, background_tasks: BackgroundTasks
) -> CrawlResult:
    job_id = str(uuid.uuid4())
    result = CrawlResult(job_id=job_id, status="pending")
    _crawl_jobs[job_id] = result

    background_tasks.add_task(_run_crawl, job_id, req)
    return result


@router.post("/agent_search")
async def agent_search(req: SearchRequest) -> SearchResult:
    results: list[FetchResult] = []

    if SEARXNG_URL:
        source = "searxng"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{SEARXNG_URL}/search",
                    json={"q": req.query, "format": "json"},
                )
                data = resp.json()
                for item in data.get("results", [])[: req.max_results]:
                    url = item.get("url", "")
                    if req.scrape_results and url:
                        fr = await smart_fetch(url)
                        results.append(fr)
                    else:
                        results.append(
                            FetchResult(
                                url=url,
                                content=item.get("content", ""),
                                title=item.get("title"),
                                confidence=0.5,
                                render_mode="static",
                            )
                        )
        except Exception as e:
            logger.warning("SearXNG search failed: %s", e)
            source = "duckduckgo"
    else:
        source = "duckduckgo"

    if source == "duckduckgo" or not results:
        source = "duckduckgo"
        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                for r in ddgs.text(req.query, max_results=req.max_results):
                    url = r.get("href", "")
                    if req.scrape_results and url:
                        fr = await smart_fetch(url)
                        results.append(fr)
                    else:
                        results.append(
                            FetchResult(
                                url=url,
                                content=r.get("body", ""),
                                title=r.get("title"),
                                confidence=0.5,
                                render_mode="static",
                            )
                        )
        except Exception as e:
            logger.warning("DuckDuckGo search failed: %s", e)

    return SearchResult(query=req.query, results=results, source=source)


@router.post("/agent_extract")
async def agent_extract(req: ExtractRequest) -> FetchResult:
    page = await smart_fetch(req.url)

    if ANTHROPIC_API_KEY:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            prompt = f"""Extract structured data from the following content according to this schema:
{json.dumps(req.schema, indent=2)}

Content:
{page.content[:10000]}

Return only valid JSON matching the schema."""
            msg = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}],
            )
            page.content = msg.content[0].text
        except Exception as e:
            logger.warning("Claude extraction failed: %s", e)
            page = _css_extract(page, req.schema)
    else:
        page = _css_extract(page, req.schema)

    return page


def _css_extract(page: FetchResult, schema: dict) -> FetchResult:
    import re

    out = {}
    for field, desc in schema.items():
        if isinstance(desc, str) and desc:
            m = re.search(rf"{field}['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]", page.content)
            if m:
                out[field] = m.group(1)
            else:
                out[field] = None
        else:
            out[field] = None
    page.content = json.dumps(out, indent=2)
    page.confidence = 0.5
    return page


@router.get("/agent_status/{job_id}")
async def agent_status(job_id: str) -> CrawlResult:
    return _crawl_jobs.get(
        job_id, CrawlResult(job_id=job_id, status="failed", error="not found")
    )


@router.get("/health")
async def health():
    redis_ok = redis_client is not None
    playwright_ok = False
    try:
        from playwright.async_api import async_playwright

        playwright_ok = True
    except Exception:
        pass
    return {
        "status": "ok",
        "redis": redis_ok,
        "playwright": playwright_ok,
        "version": "0.1.0",
    }


async def _run_crawl(job_id: str, req: CrawlRequest):
    import httpx
    from bs4 import BeautifulSoup

    result = _crawl_jobs[job_id]
    result.status = "running"

    stopper = CrawlStopper(query=req.query or "", max_pages=req.max_pages)
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(req.url, 0)]
    pages: list[FetchResult] = []

    while queue:
        url, depth = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        fr = await smart_fetch(url)
        pages.append(fr)
        stopper.add_page(fr.content)

        stop, reason = stopper.should_stop()
        result.pages = pages
        result.total_pages = len(pages)
        result.stopped_reason = reason

        if stop:
            result.status = "complete"
            return

        if depth < req.max_depth:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(url)
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for a in soup.find_all("a", href=True):
                        link = a["href"]
                        if link.startswith("http") and link not in visited:
                            queue.append((link, depth + 1))
            except Exception:
                pass

    result.status = "complete"
