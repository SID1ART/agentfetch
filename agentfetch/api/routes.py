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
from ..core.searchengine import parallel_search, search_fetch, _configure_searxng
from ..core.sanitizer import sanitize
from ..core.schema import (
    FetchResult,
    CrawlResult,
    SearchResult,
    SearchConfig,
    ScrapeConfig,
)
from ..core.stopper import CrawlStopper
from ..core.robotstxt import RobotsChecker
from ..core.job_queue import JobQueue

logger = logging.getLogger("agentfetch.api.routes")
router = APIRouter()

REDIS_URL = os.environ.get("REDIS_URL", "")
SEARXNG_URL = os.environ.get("SEARXNG_URL", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "")
CACHE_TTL = int(os.environ.get("AGENTFETCH_CACHE_TTL", "3600"))

if SEARXNG_URL:
    _configure_searxng(SEARXNG_URL)

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
    config: Optional[ScrapeConfig] = None


class BatchRequest(BaseModel):
    urls: list[str]
    engine: str = "auto"
    concurrency: int = 5
    config: Optional[ScrapeConfig] = None


class CrawlRequest(BaseModel):
    url: str
    max_depth: int = 3
    max_pages: int = 20
    query: Optional[str] = None
    strategy: str = "bfs"
    use_job_queue: bool = False


class SearchRequest(BaseModel):
    query: str
    max_results: int = 5
    scrape_results: bool = True
    sources: Optional[list[str]] = None


class ExtractRequest(BaseModel):
    url: str
    schema: dict
    provider: str = "auto"


class SearchResultItem(BaseModel):
    title: Optional[str] = None
    url: str
    content: str
    snippet: Optional[str] = None
    confidence: float = 0.5


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

    result = await smart_fetch(req.url, engine=req.engine, config=req.config)
    _set_cache(req.url, result)
    return result


@router.post("/agent_batch")
async def agent_batch(req: BatchRequest) -> list[FetchResult]:
    results = await batch_fetch(
        req.urls, concurrency=req.concurrency, config=req.config
    )
    for r in results:
        _set_cache(r.url, r)
    return results


@router.post("/agent_crawl")
async def agent_crawl(
    req: CrawlRequest, background_tasks: BackgroundTasks
) -> CrawlResult:
    job_id = str(uuid.uuid4())

    if req.use_job_queue and JobQueue.is_available():
        job_id = await JobQueue.enqueue_crawl(
            url=req.url,
            max_depth=req.max_depth,
            max_pages=req.max_pages,
            query=req.query or "",
        )
        return CrawlResult(job_id=job_id, status="queued", queued=True)

    result = CrawlResult(job_id=job_id, status="pending")
    _crawl_jobs[job_id] = result
    background_tasks.add_task(_run_crawl, job_id, req)
    return result


@router.post("/agent_search")
async def agent_search(req: SearchRequest) -> SearchResult:
    config = SearchConfig(
        max_results=req.max_results,
        sources=req.sources,
        scrape_results=req.scrape_results,
        searxng_url=SEARXNG_URL,
    )
    return await search_fetch(
        query=req.query,
        sources=config.sources,
        max_results=config.max_results,
        scrape_results=config.scrape_results,
        searxng_url=config.searxng_url,
    )


@router.post("/agent_extract")
async def agent_extract(req: ExtractRequest) -> FetchResult:
    page = await smart_fetch(req.url)

    if req.provider == "ollama" or (req.provider == "auto" and OLLAMA_URL):
        page = await _ollama_extract(page, req.schema)
    elif req.provider == "anthropic" or (req.provider == "auto" and ANTHROPIC_API_KEY):
        page = await _anthropic_extract(page, req.schema)
    else:
        page = _css_extract(page, req.schema)

    return page


async def _ollama_extract(page: FetchResult, schema: dict) -> FetchResult:
    url = OLLAMA_URL or "http://localhost:11434"
    try:
        import httpx

        prompt = f"""Extract structured data from the following content according to this schema.
Return ONLY valid JSON matching the schema, no other text.

Schema:
{json.dumps(schema, indent=2)}

Content:
{page.content[:10000]}"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{url}/api/generate",
                json={
                    "model": os.environ.get("OLLAMA_MODEL", "llama3.2"),
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                },
            )
            data = resp.json()
            page.content = data.get("response", page.content)
            page.confidence = 0.7
    except Exception as e:
        logger.warning("Ollama extraction failed: %s", e)
        page = _css_extract(page, schema)
    return page


async def _anthropic_extract(page: FetchResult, schema: dict) -> FetchResult:
    import anthropic

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        prompt = f"""Extract structured data from the following content according to this schema:
{json.dumps(schema, indent=2)}

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
        page = _css_extract(page, schema)
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
    if JobQueue.is_available():
        cached = await JobQueue.get_crawl_result(job_id)
        if cached:
            return cached
    return _crawl_jobs.get(job_id, CrawlResult(job_id=job_id, status="failed"))


@router.get("/health")
async def health():
    redis_ok = redis_client is not None
    playwright_ok = False
    ollama_ok = False
    try:
        from playwright.async_api import async_playwright

        playwright_ok = True
    except Exception:
        pass
    if OLLAMA_URL:
        try:
            import httpx

            resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
            ollama_ok = resp.status_code == 200
        except Exception:
            pass
    return {
        "status": "ok",
        "redis": redis_ok,
        "playwright": playwright_ok,
        "ollama": ollama_ok,
        "robots_check": bool(os.environ.get("AGENTFETCH_ROBOTS_CHECK")),
        "proxies_loaded": False,
        "version": "0.2.0",
    }


async def _run_crawl(job_id: str, req: CrawlRequest):
    import httpx
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin

    result = _crawl_jobs[job_id]
    result.status = "running"

    robots = RobotsChecker()
    stopper = CrawlStopper(query=req.query or "", max_pages=req.max_pages)
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(req.url, 0)]
    pages: list[FetchResult] = []

    while queue:
        url, depth = queue.pop(0)
        if stopper.is_url_seen(url):
            continue

        robots_allowed = await robots.is_allowed(url)
        if not robots_allowed:
            logger.info("Skipping %s: blocked by robots.txt", url)
            continue

        fr = await smart_fetch(url)
        stopper.mark_url_seen(url)

        dup, sim = stopper.is_duplicate_content(fr.content)
        if dup and len(pages) > 0:
            stopper.duplicates_skipped += 1
            fr.duplicate_of = pages[-1].url if pages else None
            fr.error = f"duplicate content (similarity={sim:.2f})"
            logger.info("Skipping duplicate: %s (%.2f%% similar)", url, sim * 100)

        if stopper.is_navigation(url):
            stopper.navigation_paths_skipped += 1
            fr.error = "navigation path (login, terms, etc.)"

        if not fr.error:
            pages.append(fr)
            stopper.add_page(fr.content)
            result.pages = pages
            result.total_pages = len(pages)
            result.unique_pages = len(pages)

            stop, reason = stopper.should_stop()
            result.stopped_reason = reason
            if stop:
                result.status = "complete"
                result.duplicates_skipped = stopper.duplicates_skipped
                await JobQueue.store_crawl_result(job_id, result)
                return
        else:
            result.duplicates_skipped = stopper.duplicates_skipped

        if depth < req.max_depth and not fr.error:
            links = fr.links
            if not links:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.get(url)
                        soup = BeautifulSoup(resp.text, "html.parser")
                        links = [
                            urljoin(url, a["href"])
                            for a in soup.find_all("a", href=True)
                        ]
                except Exception:
                    links = []
            for link in links:
                if link.startswith("http") and not stopper.is_url_seen(link):
                    queue.append((link, depth + 1))

    result.status = "complete"
    result.duplicates_skipped = stopper.duplicates_skipped
    await JobQueue.store_crawl_result(job_id, result)
