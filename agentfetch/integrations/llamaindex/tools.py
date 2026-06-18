try:
    from llama_index.core.tools import FunctionTool
except ImportError:
    raise ImportError(
        "llama-index is not installed. Install it with: pip install agentfetch[llamaindex]"
    )

from ...core.router import smart_fetch
from ...core.schema import CrawlResult
from ...api.routes import agent_search, CrawlRequest, _run_crawl, _crawl_jobs
import uuid


async def scrape(url: str, engine: str = "auto") -> str:
    result = await smart_fetch(url, engine=engine)
    return f"Title: {result.title}\nURL: {result.url}\n\n{result.content}"


async def search(query: str, max_results: int = 5) -> str:
    req = type(
        "SearchReq",
        (),
        {"query": query, "max_results": max_results, "scrape_results": True},
    )()
    result = await agent_search(req)
    lines = [f"Search results for: {result.query}", ""]
    for i, r in enumerate(result.results, 1):
        lines.append(f"{i}. {r.title or 'Untitled'} ({r.url})")
        lines.append(r.content[:500])
        lines.append("")
    return "\n".join(lines)


async def crawl(
    url: str, max_depth: int = 2, max_pages: int = 10, query: str = ""
) -> str:
    job_id = str(uuid.uuid4())
    req = CrawlRequest(url=url, max_depth=max_depth, max_pages=max_pages, query=query)
    result = CrawlResult(job_id=job_id, status="pending")
    _crawl_jobs[job_id] = result
    import asyncio

    asyncio.create_task(_run_crawl(job_id, req))
    return f"Crawl started. Job ID: {job_id}"


async def status(job_id: str) -> str:
    """Check the status of a crawl job."""
    cr = _crawl_jobs.get(job_id)
    if not cr:
        return f"Job {job_id}: not found"
    return (
        f"Job ID: {cr.job_id}\n"
        f"Status: {cr.status}\n"
        f"Pages: {cr.total_pages}\n"
        f"Stopped reason: {cr.stopped_reason}"
    )


class AgentFetchToolSpec:
    def to_tool_list(self) -> list:
        return [
            FunctionTool.from_defaults(
                async_fn=scrape,
                name="agentfetch_scrape",
                description="Fetch any webpage and return clean markdown",
            ),
            FunctionTool.from_defaults(
                async_fn=search,
                name="agentfetch_search",
                description="Search the web and return scraped content",
            ),
            FunctionTool.from_defaults(
                async_fn=crawl,
                name="agentfetch_crawl",
                description="Recursively crawl a website",
            ),
            FunctionTool.from_defaults(
                async_fn=status,
                name="agentfetch_status",
                description="Check the status of a crawl job by job_id",
            ),
        ]
