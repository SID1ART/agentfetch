import json
import logging
import sys

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions

logger = logging.getLogger("agentfetch.mcp")

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
                    "wait_for": {
                        "type": "string",
                        "default": "",
                        "description": "CSS selector to wait for before extracting",
                    },
                    "include_tags": {
                        "type": "string",
                        "default": "",
                        "description": "Comma-separated list of HTML tags to include",
                    },
                    "exclude_tags": {
                        "type": "string",
                        "default": "",
                        "description": "Comma-separated list of HTML tags to exclude",
                    },
                    "citation_links": {
                        "type": "boolean",
                        "default": False,
                        "description": "Replace URLs with [1], [2] citation markers",
                    },
                },
                "required": ["url"],
            },
        },
        {
            "name": "agent_crawl",
            "description": "Recursively crawl a website. Stops automatically when enough information is gathered (information saturation).",
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
            "description": "Extract structured data from a webpage. Pass schema as a JSON string with field names and descriptions.",
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
    from ..core.router import smart_fetch
    from ..core.schema import FetchResult
    from ..api.routes import _crawl_jobs, _run_crawl, agent_search

    try:
        if name == "agent_scrape":
            from ..core.schema import ScrapeConfig

            url = arguments["url"]
            engine = arguments.get("engine", "auto")
            config = ScrapeConfig(
                wait_for=arguments.get("wait_for") or None,
                include_tags=arguments.get("include_tags").split(",")
                if arguments.get("include_tags")
                else None,
                exclude_tags=arguments.get("exclude_tags").split(",")
                if arguments.get("exclude_tags")
                else None,
                citation_links=arguments.get("citation_links", False),
            )
            result = await smart_fetch(url, engine=engine, config=config)
            return [{"type": "text", "text": _format_result(result)}]

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
            return [
                {
                    "type": "text",
                    "text": f"Crawl started. Job ID: {job_id}\n\nStatus: {result.status}\nPages so far: {result.total_pages}",
                }
            ]

        elif name == "agent_search":
            query = arguments["query"]
            max_results = arguments.get("max_results", 5)
            search_req = type(
                "SearchReq",
                (),
                {"query": query, "max_results": max_results, "scrape_results": True},
            )()
            result = await agent_search(search_req)
            lines = [
                f"# Search Results for: {result.query}",
                f"Source: {result.source}",
                "",
            ]
            for i, r in enumerate(result.results, 1):
                lines.append(f"## {i}. {r.title or 'Untitled'}")
                lines.append(f"URL: {r.url}")
                lines.append(f"Confidence: {r.confidence}")
                lines.append("")
                lines.append(r.content[:2000])
                lines.append("---")
            return [{"type": "text", "text": "\n".join(lines)}]

        elif name == "agent_extract":
            url = arguments["url"]
            schema = json.loads(arguments.get("schema", "{}"))
            from ..api.routes import agent_extract as ae

            extract_req = type("ExtractReq", (), {"url": url, "schema": schema})()
            result = await ae(extract_req)
            return [
                {
                    "type": "text",
                    "text": f"# Extracted Data\n\nURL: {result.url}\n\n{result.content}",
                }
            ]

        elif name == "agent_status":
            job_id = arguments["job_id"]
            from ..api.routes import _crawl_jobs

            cr = _crawl_jobs.get(
                job_id,
                CrawlResult(job_id=job_id, status="failed", stopped_reason="not found"),
            )
            return [
                {
                    "type": "text",
                    "text": f"# Crawl Status\n\nJob ID: {cr.job_id}\nStatus: {cr.status}\nPages: {cr.total_pages}\nStopped reason: {cr.stopped_reason}",
                }
            ]

        else:
            return [{"type": "text", "text": f"Unknown tool: {name}"}]

    except Exception as e:
        logger.exception("Tool call failed")
        return [{"type": "text", "text": f"Error: {str(e)}"}]


def _format_result(r) -> str:
    lines = [
        f"# {r.title or 'Untitled'}",
        f"URL: {r.url}",
        f"Content Type: {r.content_type}",
        f"Confidence: {r.confidence}",
        f"Render Mode: {r.render_mode}",
        f"Word Count: {r.word_count}",
        f"Latency: {r.latency_ms}ms",
        f"Injection Detected: {r.injection_detected}",
        "",
        r.content,
    ]
    return "\n".join(lines)


async def stdio_server():
    from mcp.server.stdio import stdio_server
    from mcp.types import ServerCapabilities

    capabilities = ServerCapabilities(tools={})

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="agentfetch",
                server_version="0.1.0",
                capabilities=capabilities,
            ),
        )


def main():
    import asyncio

    logging.basicConfig(level=logging.INFO)
    asyncio.run(stdio_server())


if __name__ == "__main__":
    main()
