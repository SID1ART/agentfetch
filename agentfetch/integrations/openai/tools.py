"""OpenAI-compatible tool definitions for any framework using OpenAI function calling."""

from ...core.router import smart_fetch
from ...api.routes import agent_search, CrawlRequest, _run_crawl, _crawl_jobs
import asyncio
import json
import uuid


def get_tools() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "agentfetch_scrape",
                "description": "Fetch any webpage and return clean markdown. Use engine='browser' for JavaScript-heavy pages.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The URL to fetch"},
                        "engine": {
                            "type": "string",
                            "enum": ["auto", "static", "browser"],
                            "default": "auto",
                        },
                    },
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "agentfetch_search",
                "description": "Search the web and return scraped content from top results as clean markdown.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "max_results": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "agentfetch_crawl",
                "description": "Recursively crawl a website. Stops automatically when enough information is gathered.",
                "parameters": {
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
        },
    ]


async def handle_tool_call(name: str, args: dict) -> str:
    try:
        if name == "agentfetch_scrape":
            result = await smart_fetch(args["url"], engine=args.get("engine", "auto"))
            return json.dumps(
                {
                    "title": result.title,
                    "url": result.url,
                    "content": result.content,
                    "confidence": result.confidence,
                    "content_type": result.content_type,
                    "word_count": result.word_count,
                }
            )

        elif name == "agentfetch_search":
            req = type(
                "SearchReq",
                (),
                {
                    "query": args["query"],
                    "max_results": args.get("max_results", 5),
                    "scrape_results": True,
                },
            )()
            result = await agent_search(req)
            return json.dumps(
                {
                    "query": result.query,
                    "source": result.source,
                    "results": [
                        {"title": r.title, "url": r.url, "content": r.content[:2000]}
                        for r in result.results
                    ],
                }
            )

        elif name == "agentfetch_crawl":
            job_id = str(uuid.uuid4())
            req = CrawlRequest(
                url=args["url"],
                max_depth=args.get("max_depth", 2),
                max_pages=args.get("max_pages", 10),
                query=args.get("query", ""),
            )
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
            return json.dumps({"job_id": job_id, "status": "pending"})

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as e:
        return json.dumps({"error": str(e)})
