# agentfetch — Web fetch & scraping for AI agents

[![PyPI](https://img.shields.io/pypi/v/agentfetch)](https://pypi.org/project/agentfetch/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)

Fetch any webpage, crawl any site, search the web — returning clean markdown. Works with every major AI agent framework.

## Quickstart

### LangChain
```python
from agentfetch.integrations.langchain.tools import AgentFetchTools
tools = AgentFetchTools
# Use with any LangChain agent
```

### MCP (Claude, Cursor, etc.)
```bash
pip install agentfetch
agentfetch-mcp
# Configure in Claude Desktop or any MCP host
```

### REST API
```bash
pip install agentfetch
agentfetch serve
curl -X POST http://localhost:8080/agent_scrape \
  -d '{"url": "https://example.com"}'
```

## Why agentfetch?

- **One interface, all frameworks** — LangChain, LlamaIndex, CrewAI, AutoGen, OpenAI, Claude MCP, plain REST. Same functions, same output schema.
- **Smart mode routing** — Automatically detects JS-heavy SPAs and switches to headless browser. Static pages use direct HTTP. No manual engine selection.
- **Built for agent reliability** — Never raises exceptions. Always returns `FetchResult` with confidence scores, error fields, and injection detection. Agents can trust the output.
- **Information saturation crawling** — No arbitrary depth limits. CrawlStopper detects diminishing returns (vocabulary saturation, content redundancy) and stops when enough information is gathered.

## How Smart Mode works

```
                     URL
                      |
                      v
              ┌──────────────┐
              │  Static ext? │──.txt,.md,.xml,.json,.csv ──► Direct HTTP fetch
              │  (.txt,.md)  │
              └──────┬───────┘
                     │ no
                     v
              ┌──────────────┐
              │  Fast HTTP   │
              │  GET (15s)   │
              └──────┬───────┘
                     │
                     v
              ┌──────────────┐
              │  trafilatura  │
              │  extract     │
              └──────┬───────┘
                     │
                     v
              ┌──────────────────┐
              │ Check:           │
              │ • text empty?    │───yes──┐
              │ • <150 chars?    │───yes──┤
              │ • JS markers?    │───yes──┤
              │ • <noscript>>    │───yes──┤
              │   body/2?       │        │
              └────────┬─────────┘        │
                       │ no               │
                       v                  v
                 ┌──────────┐      ┌──────────────┐
                 │  Return  │      │  Playwright   │
                 │  static  │      │  headless     │
                 │  result  │      │  browser      │
                 └──────────┘      └──────────────┘
```

## The 5 tools

| Name | Description | Returns |
|------|-------------|---------|
| `agent_scrape` | Fetch any URL; auto-detects browser need | `FetchResult` |
| `agent_crawl` | Recursive crawl with saturation stopping | `CrawlResult` (async, polling via `agent_status`) |
| `agent_search` | Web search via SearXNG or DuckDuckGo + scrape results | `SearchResult` |
| `agent_extract` | Structured data extraction by JSON schema | `FetchResult` (content = JSON) |
| `agent_status` | Poll crawl job progress | `CrawlResult` |

## All integrations

| Framework | Install | Import |
|-----------|---------|--------|
| LangChain | `pip install agentfetch[langchain]` | `from agentfetch.integrations.langchain.tools import AgentFetchTools` |
| LlamaIndex | `pip install agentfetch[llamaindex]` | `from agentfetch.integrations.llamaindex.tools import AgentFetchToolSpec` |
| CrewAI | `pip install agentfetch[crewai]` | `from agentfetch.integrations.crewai.tools import scrape_tool` |
| AutoGen | `pip install agentfetch` | `from agentfetch.integrations.openai.tools import get_tools, handle_tool_call` |
| OpenAI / Gemini / Groq | `pip install agentfetch` | `from agentfetch.integrations.openai.tools import get_tools` |
| Claude MCP | `pip install agentfetch` | `agentfetch-mcp` |
| REST | `pip install agentfetch` | `agentfetch serve` |

## Self-host

```bash
docker-compose up -d
```

Starts agentfetch API (port 8080), MCP SSE server (port 8081), and Redis.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | — | Redis connection; skip caching if unset |
| `SEARXNG_URL` | — | SearXNG instance; fallback to DuckDuckGo |
| `ANTHROPIC_API_KEY` | — | For Claude-powered `agent_extract` |
| `AGENTFETCH_CACHE_TTL` | `3600` | Cache TTL in seconds |
| `AGENTFETCH_MAX_CONCURRENCY` | `5` | Max parallel requests in batch operations |
| `AGENTFETCH_INJECTION_FIREWALL` | `strict` | `strict`, `warn`, or `off` |
| `AGENTFETCH_PORT` | `8080` | API server port |

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md).
