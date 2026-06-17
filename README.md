# agentfetch

**Open-source web retrieval built for AI agents.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![Tests](https://img.shields.io/badge/tests-74%20passing-brightgreen)](https://github.com/SID1ART/agentfetch)

agentfetch is a free, local alternative to Firecrawl, Exa, and Parallel.ai. It fetches any webpage, crawls any site, and searches the web — returning clean markdown that AI agents can consume directly.

Works with **LangChain, LlamaIndex, CrewAI, AutoGen, Claude MCP, OpenAI function calling, Gemini, Groq, and plain REST.** No vendor lock-in, no API keys required.

## Install

### Standard
```bash
pip install git+https://github.com/SID1ART/agentfetch.git
```

### Cloud notebooks (Colab, Jupyter, Kaggle)
```bash
pip install https://github.com/SID1ART/agentfetch/archive/main.zip
```

### With extra integrations
```bash
pip install "agentfetch[langchain,llamaindex,crewai] @ git+https://github.com/SID1ART/agentfetch.git"
```

No PyPI account, no API tokens, no sign-up needed. GitHub is the source.

### What makes it different

- **Smart Mode Router** — detects JavaScript-heavy SPAs (Next.js, Nuxt, React) and falls back to Playwright headless browser automatically. Static pages use direct HTTP.
- **5-layer extraction pipeline** — trafilatura → newspaper3k → readability-lxml → BeautifulSoup → plain text. Best-effort extraction from any HTML.
- **Never raises exceptions** — always returns structured `FetchResult` with confidence scores, error fields, and injection detection. Agents can trust the output.
- **Information saturation crawling** — no arbitrary depth limits. CrawlStopper detects vocabulary saturation and content redundancy, stopping when enough data is gathered.
- **Prompt injection firewall** — 13 patterns detected and redacted to `[REDACTED BY AGENTFETCH]`.
- **Cloudflare bypass** — optional `curl_cffi` integration with Chrome 124 TLS fingerprint impersonation.
- **Robots.txt compliance** — optional async parser with caching, crawl-delay, and sitemap discovery.
- **Proxy rotation** — round-robin or random proxy pools with automatic failure tracking.
- **Local LLM extraction** — optional Ollama integration for structured data extraction without API costs.
- **Redis-backed job queue** — horizontal scaling for crawl operations with background workers.

## Tools

| Tool | Description |
|------|-------------|
| `agent_scrape` | Fetch any URL; auto-detects browser need. Supports ScrapeConfig (wait_for selectors, tag filtering, citation markers, proxies). |
| `agent_crawl` | Recursive crawl with information saturation stopping, robots.txt compliance, deduplication. |
| `agent_search` | Web search via SearXNG or DuckDuckGo with optional result scraping. |
| `agent_extract` | Structured data extraction by JSON schema via Ollama, Anthropic Claude, or CSS fallback. |
| `agent_status` | Poll crawl job progress (in-memory or Redis). |

## Quickstart

### LangChain

```python
from agentfetch.integrations.langchain.tools import AgentFetchTools
tools = AgentFetchTools
# Use with any LangChain agent
```

### MCP (Claude Desktop, Cursor, etc.)

```bash
pip install git+https://github.com/SID1ART/agentfetch.git
agentfetch-mcp
# configure in Claude Desktop or any MCP host
```

### REST API

```bash
pip install git+https://github.com/SID1ART/agentfetch.git
agentfetch serve
curl -X POST http://localhost:8080/agent_scrape \
  -d '{"url": "https://example.com"}'
```

### REST API

```bash
pip install git+https://github.com/SID1ART/agentfetch.git
agentfetch serve
curl -X POST http://localhost:8080/agent_scrape \
  -d '{"url": "https://example.com"}'
```

### Python library

```python
import asyncio
from agentfetch import smart_fetch
from agentfetch.core.schema import ScrapeConfig

result = asyncio.run(smart_fetch(
    "https://en.wikipedia.org/wiki/Obsession_(2025_film)",
    config=ScrapeConfig(
        wait_for=".main-content",
        exclude_tags=["nav", "footer"],
        citation_links=True,
    )
))
print(result.content)  # clean markdown
print(result.citations)  # [1], [2] URLs
```

## All integrations

| Framework | Install | Import |
|-----------|---------|--------|
| LangChain | `pip install "agentfetch[langchain] @ git+https://github.com/SID1ART/agentfetch.git"` | `from agentfetch.integrations.langchain.tools import AgentFetchTools` |
| LlamaIndex | `pip install "agentfetch[llamaindex] @ git+https://github.com/SID1ART/agentfetch.git"` | `from agentfetch.integrations.llamaindex.tools import AgentFetchToolSpec` |
| CrewAI | `pip install "agentfetch[crewai] @ git+https://github.com/SID1ART/agentfetch.git"` | `from agentfetch.integrations.crewai.tools import scrape_tool` |
| AutoGen | `pip install git+https://github.com/SID1ART/agentfetch.git` | `from agentfetch.integrations.openai.tools import get_tools` |
| OpenAI / Gemini / Groq | `pip install git+https://github.com/SID1ART/agentfetch.git` | `from agentfetch.integrations.openai.tools import get_tools` |
| Claude MCP | `pip install git+https://github.com/SID1ART/agentfetch.git` | `agentfetch-mcp` |
| Ollama | `pip install git+https://github.com/SID1ART/agentfetch.git` | `from agentfetch.integrations.ollama.tools import ollama_extract` |
| REST | `pip install git+https://github.com/SID1ART/agentfetch.git` | `agentfetch serve` |

## Configuration

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | — | Redis connection for caching + job queue |
| `SEARXNG_URL` | — | SearXNG instance for search (falls back to DuckDuckGo) |
| `ANTHROPIC_API_KEY` | — | For Claude-powered `agent_extract` |
| `OLLAMA_URL` | — | Ollama endpoint for local LLM extraction |
| `OLLAMA_MODEL` | `llama3.2` | Ollama model name |
| `AGENTFETCH_CACHE_TTL` | `3600` | Cache TTL in seconds |
| `AGENTFETCH_STATIC_TIMEOUT` | `15` | HTTP fetch timeout (seconds) |
| `AGENTFETCH_BROWSER_TIMEOUT` | `30` | Playwright browser timeout (seconds) |
| `AGENTFETCH_MAX_RETRIES` | `2` | Max retries for failed requests |
| `AGENTFETCH_DOMAIN_DELAY` | `0.5` | Delay between requests to same domain |
| `AGENTFETCH_ROBOTS_CHECK` | `false` | Enable robots.txt compliance |
| `AGENTFETCH_PROXY_LIST` | — | Comma-separated proxy URLs or JSON array |
| `AGENTFETCH_PROXY_STRATEGY` | `round-robin` | `round-robin` or `random` |
| `AGENTFETCH_COOKIES_FILE` | — | Path to cookies file (Netscape or JSON) |
| `AGENTFETCH_PORT` | `8080` | API server port |

## Self-host

```bash
docker-compose up -d
# Starts API (port 8080), MCP SSE (port 8081), Redis
# Optional crawl worker:
docker compose --profile worker up -d
```

## Architecture

```
                         ┌─────────────┐
                         │   Smart     │
                         │   URL       │
                         │   Router    │
                         └──────┬──────┘
                                │
              ┌─────────────────┼──────────────────┐
              │                 │                   │
              ▼                 ▼                   ▼
      ┌────────────┐   ┌──────────────┐   ┌────────────────┐
      │  Static    │   │  Cloudflare  │   │   Playwright   │
      │  HTTP      │   │  bypass      │   │   Headless     │
      │  (httpx)   │   │  (curl_cffi) │   │   Browser      │
      └─────┬──────┘   └──────┬───────┘   └───────┬────────┘
            │                 │                    │
            └─────────────────┼────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  Extraction     │
                    │  Pipeline       │
                    │  trafilatura →  │
                    │  newspaper3k →  │
                    │  readability →  │
                    │  BS4 → plain    │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  Sanitizer      │
                    │  (13 injection  │
                    │   patterns)     │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  Post-process   │
                    │  • Citations    │
                    │  • Dedup check  │
                    │  • Max length   │
                    │  • Markdown     │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   FetchResult   │
                    │   Pydantic      │
                    │   response      │
                    └─────────────────┘
```

## Tests

```bash
pip install -e ".[all]"
pytest tests/ -v
# 74 tests passing
```

## License

MIT — free for any use, including commercial.
