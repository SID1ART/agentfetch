try:
    from crewai.tools import tool
except ImportError:
    raise ImportError(
        "crewai is not installed. Install it with: pip install agentfetch[crewai]"
    )

from ...core.router import smart_fetch
from ...core.mapper import smart_map
from ...core.schema import CrawlResult, MapConfig
from ...api.routes import agent_search, CrawlRequest, _run_crawl, _crawl_jobs
import uuid


@tool("Scrape a webpage")
async def scrape_tool(url: str) -> str:
    """Fetch any webpage and return clean markdown content."""
    result = await smart_fetch(url)
    return f"Title: {result.title}\nURL: {result.url}\n\n{result.content}"


@tool("Search the web")
async def search_tool(query: str) -> str:
    """Search the web and return scraped content from top results."""
    from ...api.routes import SearchRequest

    req = SearchRequest(query=query, max_results=5, scrape_results=True)
    result = await agent_search(req)
    lines = [f"Search results for: {result.query}", ""]
    for i, r in enumerate(result.results, 1):
        lines.append(f"{i}. {r.title or 'Untitled'} ({r.url})")
        lines.append("")
    return "\n".join(lines)


@tool("Crawl a website")
async def crawl_tool(url: str) -> str:
    """Recursively crawl a website and gather information."""
    job_id = str(uuid.uuid4())
    req = CrawlRequest(url=url, max_depth=2, max_pages=10)
    result = CrawlResult(job_id=job_id, status="pending")
    _crawl_jobs[job_id] = result
    import asyncio

    asyncio.create_task(_run_crawl(job_id, req))
    return f"Crawl started. Job ID: {job_id}"


@tool("Map website URLs")
async def map_tool(url: str) -> str:
    """Discover all URLs on a website. First tries sitemap.xml, then BFS crawling."""
    result = await smart_map(url)
    lines = [
        f"Mapped: {result.base_url}",
        f"Sources: {', '.join(result.sources)}",
        f"Total URLs: {result.total}",
        "",
    ]
    lines.extend(result.links)
    return "\n".join(lines)


@tool("Check crawl status")
async def status_tool(job_id: str) -> str:
    """Check the status of a crawl job. Provide the job_id returned by the crawl tool."""
    from ...api.routes import _crawl_store

    cr = _crawl_jobs.get(job_id) or _crawl_store.get(job_id)
    if not cr:
        return f"Job {job_id}: not found"
    return (
        f"Job ID: {cr.job_id}\n"
        f"Status: {cr.status}\n"
        f"Pages: {cr.total_pages}\n"
        f"Stopped reason: {cr.stopped_reason}"
    )
