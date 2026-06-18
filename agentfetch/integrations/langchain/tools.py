try:
    from langchain_core.tools import tool
except ImportError:
    raise ImportError(
        "langchain is not installed. Install it with: pip install agentfetch[langchain]"
    )

from ...core.router import smart_fetch, batch_fetch
from ...core.schema import FetchResult


@tool
async def agentfetch_scrape(url: str, engine: str = "auto") -> str:
    """Fetch any webpage and return clean markdown content.

    Args:
        url: The URL to fetch.
        engine: 'auto', 'static', or 'browser'.
    """
    result = await smart_fetch(url, engine=engine)
    return _format_result(result)


@tool
async def agentfetch_search(query: str, max_results: int = 5) -> str:
    """Search the web and return scraped content from top results.

    Args:
        query: Search query string.
        max_results: Maximum number of results to return.
    """
    from ...api.routes import agent_search

    req = type(
        "SearchReq",
        (),
        {"query": query, "max_results": max_results, "scrape_results": True},
    )()
    result = await agent_search(req)
    lines = [f"Search results for: {result.query} (source: {result.source})", ""]
    for i, r in enumerate(result.results, 1):
        lines.append(f"{i}. {r.title or 'Untitled'}")
        lines.append(f"   URL: {r.url}")
        lines.append(f"   {r.content[:500]}")
        lines.append("")
    return "\n".join(lines)


@tool
async def agentfetch_crawl(
    url: str, max_depth: int = 2, max_pages: int = 10, query: str = ""
) -> str:
    """Recursively crawl a website and gather information.

    Args:
        url: Starting URL.
        max_depth: Maximum crawl depth.
        max_pages: Maximum pages to crawl.
        query: Optional search query for relevance.
    """
    from ...api.routes import CrawlRequest, _run_crawl, _crawl_jobs
    import uuid

    job_id = str(uuid.uuid4())
    req = CrawlRequest(url=url, max_depth=max_depth, max_pages=max_pages, query=query)
    result = type(
        "CrawlResult",
        (),
        {
            "job_id": job_id,
            "status": "pending",
            "pages": [],
            "total_pages": 0,
            "stopped_reason": None,
        },
    )()
    _crawl_jobs[job_id] = result
    import asyncio

    asyncio.create_task(_run_crawl(job_id, req))
    return f"Crawl started. Job ID: {job_id}"


def _format_result(r) -> str:
    lines = [
        f"Title: {r.title or 'Untitled'}",
        f"URL: {r.url}",
        f"Type: {r.content_type} | Confidence: {r.confidence} | Words: {r.word_count}",
        "",
        r.content,
    ]
    return "\n".join(lines)


AgentFetchTools = [agentfetch_scrape, agentfetch_search, agentfetch_crawl]
