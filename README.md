# agentfetch

**Open-source web retrieval built for AI agents.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![Tests](https://img.shields.io/badge/tests-116%20passing-brightgreen)](https://github.com/SID1ART/agentfetch)

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
pip install "agentfetch[search] @ git+https://github.com/SID1ART/agentfetch.git"   # adds Google search engine
```

No PyPI account, no API tokens, no sign-up needed. GitHub is the source.

### What makes it different

- **Smart Mode Router** — detects JavaScript-heavy SPAs (Next.js, Nuxt, React) and falls back to Playwright headless browser automatically. Static pages use direct HTTP.
- **5-layer extraction pipeline** — trafilatura → newspaper3k → readability-lxml → BeautifulSoup → plain text. Best-effort extraction from any HTML.
- **Never raises exceptions** — always returns structured `FetchResult` with confidence scores, error fields, and injection detection. Agents can trust the output.
- **Post-extraction quality check** — detects SPA shell text, low prose ratio, missing sentence structure, and downgrades confidence so agents can retry with browser engine.
- **In-memory LRU cache** — deduplicates repeated URL fetches within a session. Configurable size/TTL via env vars. No Redis required.
- **Information saturation crawling** — no arbitrary depth limits. CrawlStopper detects vocabulary saturation and content redundancy, stopping when enough data is gathered.
- **Persistent crawl store** — SQLite-backed job persistence when Redis is not configured. Results survive process restarts.
- **Prompt injection firewall** — 13 patterns detected and redacted to `[REDACTED BY AGENTFETCH]`.
- **Cloudflare bypass** — optional `curl_cffi` integration with 12 TLS fingerprint profiles (Chrome 99–124, Safari 15/17) and auto-rotation.
- **Browser stealth** — optional `playwright-stealth` integration for advanced anti-detection (WebGL vendor, canvas fingerprint, navigator.webdriver removal). Enabled by default.
- **Robots.txt compliance** — optional async parser with caching, crawl-delay, and sitemap discovery.
- **Proxy rotation** — round-robin or random proxy pools with automatic failure tracking.
- **Local LLM extraction** — optional Ollama integration for structured data extraction without API costs.
- **Redis-backed job queue** — horizontal scaling for crawl operations with background workers.

## Tools

| Tool | Description |
|------|-------------|
| `agent_scrape` | Fetch any URL; auto-detects browser need. Supports ScrapeConfig (wait_for selectors, tag filtering, citation markers, proxies, JA3 profile). |
| `agent_crawl` | Recursive crawl with information saturation stopping, robots.txt compliance, deduplication. |
| `agent_search` | Web search via SearXNG, DuckDuckGo, Google, or Bing with optional result scraping. |
| `agent_extract` | Structured data extraction by JSON schema via Ollama, Anthropic Claude, or CSS fallback. |
| `agent_map` | Discover all URLs on a website via sitemap.xml and BFS crawling. |
| `agent_status` | Poll crawl job progress (in-memory or Redis). |

### Library API

| Function | Description |
|----------|-------------|
| `smart_fetch(url, config=)` | Fetch a single URL; auto-detects browser need. Returns `FetchResult`. |
| `batch_fetch(urls, concurrency=)` | Fetch multiple URLs concurrently. Returns `list[FetchResult]`. |
| `search_fetch(query, sources=, max_results=)` | Search and optionally scrape results. Returns `SearchResult`. |
| `parallel_search(query, sources=, max_results=)` | Search engine results without scraping. Returns `tuple[list[EngineResult], list[str], dict[str, str]]`. |

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

### Python library

```python
import asyncio
from agentfetch import smart_fetch, search_fetch
from agentfetch.core.schema import ScrapeConfig

# Fetch a single URL
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

# Search with multiple engines
sr = asyncio.run(search_fetch(
    "latest AI news",
    sources=["duckduckgo", "google", "bing"],
    max_results=5,
))
print(sr.results)      # list[FetchResult]
print(sr.errors)       # per-engine errors, e.g. {"google": "rate limited (429)"}
print(sr.sources_used) # engines that returned results
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

## Schema reference

### `ScrapeConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `wait_for` | `str` | `None` | CSS selector to wait for before extracting |
| `include_tags` | `list[str]` | `None` | Only extract these HTML tags |
| `exclude_tags` | `list[str]` | `None` | Skip these HTML tags during extraction |
| `viewport` | `dict` | `None` | Browser viewport `{width, height}` |
| `js_wait_ms` | `int` | `0` | Extra JS wait time in milliseconds |
| `scrape_links` | `bool` | `True` | Extract links from page |
| `max_content_length` | `int` | `50000` | Truncate content beyond this length |
| `citation_links` | `bool` | `False` | Track citation markers `[1]`, `[2]` |
| `proxy` | `str` | `None` | Proxy URL for this request |
| `cookies` | `list[dict]` | `None` | Cookies to include in browser session |
| `headers` | `dict[str,str]` | `None` | Custom HTTP headers |
| `ja3` | `str` | `None` | JA3 TLS profile for `curl_cffi` bypass (e.g. `"chrome124"`) |
| `stealth` | `bool` | `True` | Enable browser stealth evasions (playwright-stealth if available) |
| `actions` | `list[Action]` | `[]` | Action chain to execute before extraction (click, scroll, type, wait, press, select, screenshot, hover, custom_js) |
| `screenshot` | `bool` | `False` | Capture a full-page final screenshot (PNG, base64-encoded in `screenshot_data`) |

### `FetchResult`

| Field | Type | Description |
|-------|------|-------------|
| `url` | `str` | Requested URL |
| `content` | `str` | Extracted markdown content |
| `title` | `str` | Page title |
| `confidence` | `float` | Extraction quality (0.0–1.0) |
| `content_type` | `str` | Detected type (article, blog, product, etc.) |
| `word_count` | `int` | Word count of extracted content |
| `render_mode` | `str` | Renderer used: `static`, `browser`, or `bypass` |
| `latency_ms` | `int` | Total request time in milliseconds |
| `cached` | `bool` | Whether result came from cache |
| `injection_detected` | `bool` | Prompt injection was found and redacted |
| `links` | `list[str]` | Links extracted from the page |
| `error` | `str` | Error message if the fetch failed |
| `duplicate_of` | `str` | URL this content was deduplicated against |
| `retries` | `int` | Number of retries performed |
| `citations` | `list[str]` | Citation URLs when `citation_links=True` |
| `robots_allowed` | `bool` | Whether robots.txt permitted the fetch |
| `proxy_used` | `str` | Proxy used for this request |
| `normalized_url` | `str` | Normalized version of the requested URL |
| `screenshot_data` | `str` | Base64-encoded final PNG screenshot (when `screenshot=True` in ScrapeConfig) |
| `screenshots` | `list[str]` | Base64-encoded PNG screenshots from mid-flow screenshot actions (when `store_output=True`) |

### `Action`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | `str` | — | Action type: `click`, `scroll`, `type`, `wait`, `press`, `select`, `screenshot`, `hover`, or `custom_js` |
| `selector` | `str` | `None` | CSS selector for `click`, `type`, `scroll`, `press`, `select`, `hover` actions |
| `value` | `str` | `None` | Value: text for `type`, key for `press`, ms for `wait`, pixels for `scroll`, option value for `select`, JS code for `custom_js` |
| `timeout` | `int` | `5000` | Timeout in ms for selector waits |
| `store_output` | `bool` | `False` | When `True`, stores `screenshot` action output in `FetchResult.screenshots` list |

**Action details:**
- **click** — clicks a CSS selector, waits for `networkidle` afterward
- **scroll** — scrolls to selector, `"bottom"`, `"top"`, or by N pixels
- **type** — fills an input field with `value`
- **wait** — waits N milliseconds (`value`)
- **press** — presses a key (`value`, default `"Enter"`), waits for `networkidle`
- **select** — selects a `<select>` option by `value`
- **screenshot** — captures a full-page PNG; stored in `screenshots[]` if `store_output=True`
- **hover** — hovers over a CSS selector
- **custom_js** — runs arbitrary JavaScript from `value` on the page, waits for `networkidle`

**Examples:**
```python
# Hover to reveal dropdown, then click
actions = [
    Action(type="hover", selector="#nav-menu"),
    Action(type="wait", value="500"),
    Action(type="click", selector="#nav-menu .dropdown-item"),
]

# Run custom JS and capture mid-flow screenshot
actions = [
    Action(type="custom_js", value="document.querySelector('.paywall')?.remove()"),
    Action(type="screenshot", store_output=True),
]

# Full-page final screenshot
config = ScrapeConfig(screenshot=True, actions=[...])
```

### `SearchConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_results` | `int` | `5` | Max results per engine |
| `sources` | `list[str]` | `None` | Engines: `duckduckgo`, `google`, `bing`, `searxng`, `brave`, `serpapi` |
| `scrape_results` | `bool` | `True` | Fetch full content of each result |
| `searxng_url` | `str` | `""` | Self-hosted SearXNG instance URL |
| `topic` | `str` | `"general"` | Search topic: `general`, `news`, or `finance` |
| `time_range` | `str` | `None` | Time filter: `day`, `week`, `month`, or `year` |
| `country` | `str` | `None` | Boost results from a country (e.g. `"united states"`, `"united kingdom"`) |
| `include_answer` | `bool` | `False` | Include an LLM-generated answer via Ollama or Anthropic |

### `SearchResult`

| Field | Type | Description |
|-------|------|-------------|
| `query` | `str` | Original search query |
| `results` | `list[FetchResult]` | Search results with extracted content |
| `source` | `str` | Concatenated engine names used |
| `sources_used` | `list[str]` | Engines that returned results |
| `suggestions` | `list[str]` | Search suggestions (if available) |
| `total_results` | `int` | Total deduplicated result count |
| `errors` | `dict[str,str]` | Per-engine error messages (e.g. `{"google": "rate limited (429)"}`) |
| `answer` | `str` | LLM-generated answer when `include_answer=True` in SearchConfig |

### `MapConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_depth` | `int` | `2` | Maximum crawl depth for link discovery |
| `max_pages` | `int` | `100` | Maximum URLs to discover |
| `include_patterns` | `list[str]` | `None` | Regex patterns to include only matching paths |
| `exclude_patterns` | `list[str]` | `None` | Regex patterns to exclude matching paths |
| `include_domains` | `list[str]` | `None` | Only include URLs from these domains |
| `exclude_domains` | `list[str]` | `None` | Exclude URLs from these domains |
| `respect_robots` | `bool` | `True` | Respect robots.txt during crawl discovery |

### `MapResult`

| Field | Type | Description |
|-------|------|-------------|
| `base_url` | `str` | The root URL that was mapped |
| `links` | `list[str]` | Discovered URLs |
| `total` | `int` | Total number of discovered URLs |
| `sources` | `list[str]` | Discovery methods used (`sitemap`, `crawl`) |

## Configuration

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | — | Redis connection for caching + job queue |
| `SEARXNG_URL` | — | SearXNG instance for search (falls back to DuckDuckGo + Google + Bing) |
| `BRAVE_SEARCH_API_KEY` | — | Brave Search API key (enables `brave` engine, preferred over DuckDuckGo) |
| `SERPAPI_KEY` | — | SerpAPI key (enables `serpapi` engine, preferred over Google scraping) |
| `GOOGLE_API_KEY` | — | Google Custom Search API key (used by `google` engine when both key and CX are set) |
| `GOOGLE_CX` | — | Google Custom Search CX (required with `GOOGLE_API_KEY`) |
| `ANTHROPIC_API_KEY` | — | For Claude-powered `agent_extract` |
| `ANTHROPIC_MODEL` | `claude-3-haiku-20240307` | Claude model name for extraction |
| `OLLAMA_URL` | — | Ollama endpoint for local LLM extraction |
| `OLLAMA_MODEL` | `llama3.2` | Ollama model name |
| `AGENTFETCH_CACHE_TTL` | `300` | In-memory LRU cache TTL (seconds) |
| `AGENTFETCH_CACHE_SIZE` | `100` | Max entries in in-memory LRU cache |
| `AGENTFETCH_STATIC_TIMEOUT` | `15` | HTTP fetch timeout (seconds) |
| `AGENTFETCH_BROWSER_TIMEOUT` | `30` | Playwright browser timeout (seconds) |
| `AGENTFETCH_MAX_RETRIES` | `2` | Max retries for failed requests |
| `AGENTFETCH_DOMAIN_DELAY` | `0.5` | Delay between requests to same domain |
| `AGENTFETCH_ROBOTS_CHECK` | `false` | Enable robots.txt compliance |
| `AGENTFETCH_PROXY_LIST` | — | Comma-separated proxy URLs or JSON array |
| `AGENTFETCH_PROXY_STRATEGY` | `round-robin` | `round-robin` or `random` |
| `AGENTFETCH_COOKIES_FILE` | — | Path to cookies file (Netscape or JSON) |
| `AGENTFETCH_PORT` | `8080` | API server port |
| `AGENTFETCH_JA3_PROFILE` | — | JA3 TLS profile override for `curl_cffi` |
| `AGENTFETCH_STEALTH` | `true` | Enable browser stealth evasions in Playwright |
| `AGENTFETCH_STEALTH_BASIC_FALLBACK` | `true` | Fall back to non-stealth browser if stealth fails |
| `AGENTFETCH_CRAWL_DB` | `agentfetch_crawl.db` | SQLite path for crawl job persistence |
| `AGENTFETCH_MIN_PROSE_RATIO` | `0.4` | Minimum alpha-char ratio for quality check |
| `AGENTFETCH_MIN_WORDS` | `10` | Minimum word count for quality check |

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
# 98 tests passing
```

## License

MIT — free for any use, including commercial.
