import json
import logging
import uuid

from mcp.server import Server
from mcp.server.models import InitializationOptions

from ..core.router import smart_fetch
from ..core.schema import FetchResult, CrawlResult
from ..api.routes import _crawl_jobs, _run_crawl, agent_search

logger = logging.getLogger("agentfetch.mcp.sse")

server = Server("agentfetch")


@server.list_tools()
async def list_tools():
    return [
        {
            "name": "agent_scrape",
            "description": "Fetch any webpage and return clean markdown. Use engine='browser' for JavaScript-heavy pages.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "engine": {"type": "string", "default": "auto"},
                },
                "required": ["url"],
            },
        },
        {
            "name": "agent_crawl",
            "description": "Recursively crawl a website. Stops automatically when enough information is gathered.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "max_depth": {"type": "integer", "default": 2},
                    "max_pages": {"type": "integer", "default": 10},
                    "query": {"type": "string", "default": ""},
                },
                "required": ["url"],
            },
        },
        {
            "name": "agent_search",
            "description": "Search the web and return scraped content from top results as clean markdown.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
        {
            "name": "agent_extract",
            "description": "Extract structured data from a webpage.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "schema": {"type": "string"},
                },
                "required": ["url", "schema"],
            },
        },
        {
            "name": "agent_status",
            "description": "Check the status of an async crawl job.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                },
                "required": ["job_id"],
            },
        },
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list:
    try:
        if name == "agent_scrape":
            url = arguments["url"]
            engine = arguments.get("engine", "auto")
            result = await smart_fetch(url, engine=engine)
            lines = [
                f"# {result.title or 'Untitled'}",
                f"URL: {result.url}",
                f"Confidence: {result.confidence}",
                f"Render Mode: {result.render_mode}",
                f"Word Count: {result.word_count}",
                "",
                result.content,
            ]
            return [{"type": "text", "text": "\n".join(lines)}]

        elif name == "agent_crawl":
            from ..api.routes import CrawlRequest

            req = CrawlRequest(
                url=arguments["url"],
                max_depth=arguments.get("max_depth", 2),
                max_pages=arguments.get("max_pages", 10),
                query=arguments.get("query", ""),
            )
            job_id = str(uuid.uuid4())
            result = CrawlResult(job_id=job_id, status="pending")
            _crawl_jobs[job_id] = result
            import asyncio

            asyncio.create_task(_run_crawl(job_id, req))
            msg = f"Crawl started. Job ID: {job_id}\nStatus: {result.status}\nPages so far: {result.total_pages}"
            return [{"type": "text", "text": msg}]

        elif name == "agent_search":
            query = arguments["query"]
            max_results = arguments.get("max_results", 5)
            from ..api.routes import SearchRequest

            req = SearchRequest(
                query=query, max_results=max_results, scrape_results=True
            )
            result = await agent_search(req)
            lines = [
                f"# Search Results for: {result.query}",
                f"Source: {result.source}",
                "",
            ]
            for i, r in enumerate(result.results, 1):
                lines.append(f"## {i}. {r.title or 'Untitled'}")
                lines.append(f"URL: {r.url}")
                lines.append(r.content[:2000])
                lines.append("---")
            return [{"type": "text", "text": "\n".join(lines)}]

        elif name == "agent_extract":
            from ..api.routes import agent_extract as ae, ExtractRequest

            url = arguments["url"]
            schema_str = arguments.get("schema", "{}")
            schema_dict = (
                json.loads(schema_str) if isinstance(schema_str, str) else schema_str
            )
            req = ExtractRequest(url=url, extract_schema=schema_dict, provider="auto")
            result = await ae(req)
            return [{"type": "text", "text": f"# Extracted Data\n\n{result.content}"}]

        elif name == "agent_status":
            job_id = arguments["job_id"]
            cr = _crawl_jobs.get(
                job_id,
                CrawlResult(job_id=job_id, status="failed", stopped_reason="not found"),
            )
            msg = f"Job ID: {cr.job_id}\nStatus: {cr.status}\nPages: {cr.total_pages}\nStopped reason: {cr.stopped_reason}"
            return [{"type": "text", "text": msg}]

        return [{"type": "text", "text": f"Unknown tool: {name}"}]

    except Exception as e:
        logger.exception("Tool call failed")
        return [{"type": "text", "text": f"Error: {str(e)}"}]


async def sse_server():
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route
    import uvicorn

    sse = SseServerTransport("/messages")

    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as (
            read_stream,
            write_stream,
        ):
            from mcp.types import ServerCapabilities

            capabilities = ServerCapabilities(tools={})
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="agentfetch",
                    server_version="0.1.0",
                    capabilities=capabilities,
                ),
            )

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages", app=sse.handle_post_message),
        ],
    )

    config = uvicorn.Config(app, host="0.0.0.0", port=8081)
    server = uvicorn.Server(config)
    await server.serve()


def main():
    import asyncio

    logging.basicConfig(level=logging.INFO)
    asyncio.run(sse_server())


if __name__ == "__main__":
    main()
