# agentfetch — Specification

agentfetch is a Python library purpose-built for AI agents to fetch, extract, search, and structure web content. It provides a unified pipeline with multi-engine fallback, extraction cascades, search integration, and structured output — all exposed as simple async functions that framework integrations (LangChain, LlamaIndex, CrewAI, OpenAI, MCP) can consume directly.

---

## 1. Core Architecture

```
User/Agent
  │
  ├─ smart_fetch(url)          ──►  router.py   ──► static fetch (httpx / curl_cffi)
  │                                              ──► Cloudflare bypass
  │                                              ──► Browser render (Playwright)
  │                                              ──► Quality validation
  │                                              ──► Cache (TTL-based, config-aware)
  │                                              ──► Post-extraction (highlights / schema)
  │
  ├─ batch_fetch(urls)         ──►  router.py   ──► concurrent smart_fetch with semaphore
  │
  ├─ parallel_search(query)    ──► searchengine  ──► DuckDuckGo / Google / Bing / Brave /
  │                                        │           SearXNG / SerpAPI (async parallel)
  │                                        └─► dedup + merge → EngineResult[]
  │
  ├─ stream_search(query)      ──► searchengine  ──► async generator yielding EngineResults
  │
  ├─ search_fetch(query)       ──► searchengine  ──► parallel_search → smart_fetch each URL
  │
  ├─ extract_content(html)     ──►  extractor.py ──► trafilatura → newspaper3k
  │                                              ──► readability → bs4 → plaintext
  │
  ├─ extract_highlights(text)  ──►  extractor.py ──► TF-based sentence scoring → top-K
  │
  └─ extract_structured(text, schema)
                               ──►  extractor.py ──► field matching + type coercion
                                                    ──► proximity-scored number extraction
```

### Pipeline Flow for a Single Fetch

```
smart_fetch(url, config)
  │
  ├─ 1. Normalize URL
  ├─ 2. Cache lookup (key = url + config.extract_highlights + hash(config.output_schema))
  │     └─ hit → apply post-extraction, return
  ├─ 3. robots.txt check
  ├─ 4. Route selection (category → engine override)
  │
  ├─ 5. Engine loop:
  │     ├─ static:     httpx → curl_cffi (TLS fingerprint) → retry with backoff
  │     ├─ bypass:     curl_cffi impersonation (JA3 profiles)
  │     ├─ browser:    Playwright (stealth / basic) with fingerprint rotation
  │     └─ cloudflare: curl_cffi challenge solver
  │
  ├─ 6. Extract:     trafilatura → newspaper3k → readability → bs4 → plaintext
  ├─ 7. Sanitize:    prompt injection detection + removal
  ├─ 8. Validate:    prose ratio, word count, sentence structure → confidence score
  ├─ 9. Cache:       store result (config-aware key)
  └─ 10. Post-extract:
        ├─ highlights:  TF-based sentence scoring → top 5 sentences
        └─ structured:  field-by-field extraction with proximity scoring
```

---

## 2. Public API Surface

### Fetch Functions

| Function | Signature | Returns |
|---|---|---|
| `smart_fetch` | `(url, engine="auto", use_cache=True, cache_ttl=3600, cookies=None, config=None)` | `FetchResult` |
| `batch_fetch` | `(urls, concurrency=5, config=None)` | `list[FetchResult]` |

### Search Functions

| Function | Signature | Returns |
|---|---|---|
| `parallel_search` | `(query, sources=None, max_results=5, searxng_url="", depth="auto", category="auto")` | `(list[EngineResult], list[str], dict[str,str])` |
| `search_fetch` | `(query, sources=None, max_results=5, scrape_results=True, searxng_url="", config=None, category="auto", depth="auto")` | `SearchResult` |
| `stream_search` | `(query, sources=None, max_results=5, searxng_url="")` | `AsyncIterator[EngineResult]` |
| `generate_query_variations` | `(query)` | `list[str]` |

### Extraction Functions

| Function | Signature | Returns |
|---|---|---|
| `extract_content` | `(html, url="", config=None)` | `(str, str, list[str])` |
| `extract_highlights` | `(text, max_sentences=5)` | `list[str]` |
| `extract_structured` | `(text, schema)` | `Optional[dict]` |
| `detect_content_type` | `(html, url)` | `str` |
| `sanitize` | `(text, url)` | `(str, bool)` |

### Supporting Functions

| Function | Signature |
|---|---|
| `_configure_searxng` | `(url)` |
| `normalize_url` | `(url)` |
| `content_hash` | `(text)` |
| `is_near_duplicate` | `(hash1, hash2, threshold=3)` |
| `simhash_fingerprint` | `(text)` |

### Pydantic Models

**`ScrapeConfig`** — Per-request fetch configuration:
```
wait_for, include_tags, exclude_tags, viewport, js_wait_ms, scrape_links,
max_content_length, citation_links, proxy, cookies, headers, ja3, stealth,
category, extract_highlights, output_schema
```

**`FetchResult`** — Single page fetch result:
```
url, content, title, confidence, content_type, word_count, render_mode,
latency_ms, cached, injection_detected, links, error, duplicate_of, retries,
normalized_url, citations, robots_allowed, proxy_used, highlights, structured_output
```

**`SearchResult`** — Full search + scrape result:
```
query, results (list[FetchResult]), source, sources_used, suggestions,
total_results, errors
```

**`EngineResult`** (dataclass) — Raw search engine hit:
```
title, url, snippet, source
```

**`CrawlResult`** — Multi-page crawl job:
```
job_id, status, pages, total_pages, unique_pages, duplicates_skipped,
stopped_reason, queued
```

---

## 3. Features Built

### 3.1 Multi-Engine Fetch with Fallback Chain

```
httpx (default)
  └─ on failure → curl_cffi (TLS fingerprint impersonation)
       ├─ on Cloudflare → Cloudflare bypass via curl_cffi
       └─ on JS-heavy page → Playwright (stealth / basic)
            └─ stealth fails → basic Playwright fallback
```

- 8 browser fingerprint profiles rotated randomly
- 6 JA3 TLS profiles for curl_cffi impersonation
- Domain-level throttling (configurable delay)
- Retry with exponential backoff (configurable max retries)
- Proxy rotation via ProxyManager
- robots.txt compliance (optional, cached)

### 3.2 Category-Based Routing

Maps content categories to engine overrides and confidence floors:

| Category | Engine Override | Confidence Floor |
|---|---|---|
| `article` | auto | 0.5 |
| `news` | auto | 0.4 |
| `company` | auto | 0.3 |
| `people` | **browser** | 0.2 |
| `research_paper` | auto | 0.4 |
| `personal_site` | auto | 0.4 |
| `docs` | **static** | 0.6 |
| `product` | auto | 0.3 |
| `listing` | **static** | 0.3 |
| `financial_report` | auto | 0.4 |

Set via `ScrapeConfig(category="news")`. Unknown categories default to `"auto"` engine with no floor.

### 3.3 Multi-Engine Search

6 search engines supported, queried in parallel:

| Engine | Requires | Notes |
|---|---|---|
| DuckDuckGo | `duckduckgo_search` | Free, no API key |
| Google | `googlesearch-python` | Free, no API key |
| Google API | `GOOGLE_API_KEY` + `GOOGLE_CX` env vars | 100 queries/day free |
| Bing | (none; HTML scrape) | Free, no API key |
| Brave | `BRAVE_SEARCH_API_KEY` env var | 2,000 queries/month free |
| SerpAPI | `SERPAPI_KEY` env var | 100 queries/month free |
| SearXNG | `SEARXNG_URL` env var | Self-hosted |

Category query modifiers (e.g., `news` appends `"latest OR today OR breaking"`) and deep search (generates 3-4 query variations) are built in.

### 3.4 Content Extraction Cascade

```
trafilatura (best quality)
  └─ on failure → newspaper3k
       └─ on failure → readability-lxml
            └─ on failure → bs4 (<p>, <article> tags)
                 └─ on failure → plaintext (all text)
```

- `include_tags` / `exclude_tags` for custom extraction
- `max_content_length` truncation
- Markdown conversion via `markdownify`
- Citation marker injection (`[1]`, `[2]`, ...)

### 3.5 Highlights Extraction

TF-based sentence scoring:
1. Split text into sentences
2. Build word frequency counter
3. Score each sentence by average word frequency
4. Return top-K sentences (default 5)

### 3.6 Structured Output Extraction

`extract_structured(text, schema)` extracts typed fields:
- **Schema format**: JSON Schema `{"type":"object","properties":{...}}` or shorthand `{"field":"description"}`
- **Field types**: `string`, `number`, `integer`, `boolean`
- **Matching**: proximity-scored (field name + description against each line)
- **Number parsing**: handles `"500 million"` → 500000000, `"1,234"` → 1234, with word-boundary safeguards
- **Boolean parsing**: `Key: True`, `Key=yes`, etc.
- **Nested support**: propagates `properties` through `extract_by_schema`

### 3.7 Quality Validation Pipeline

Every fetched result passes through:
- SPA shell text detection (loading screens, JS-required messages)
- Prose ratio check (alpha chars / total chars ≥ 0.4)
- Minimum word count (≥ 10)
- Sentence structure check
- Prompt injection detection

### 3.8 Config-Aware Cache

- In-memory LRU cache with TTL (default 100 entries, 300s TTL)
- Cache key includes relevant config: `f"{url}|hl={extract_highlights}|sh={schema_hash}"`
- Post-extraction always re-applied on cache hit

### 3.9 Streaming Search

`stream_search(query)` yields `EngineResult` objects as each search engine responds, using `asyncio.as_completed()` for true streaming.

### 3.10 Anti-Detection

- User-agent rotation (8 modern browser UAs)
- TLS fingerprint impersonation via curl_cffi (Chrome 99-124, Safari 15/17)
- Playwright stealth mode with `playwright-stealth` (optional)
- Viewport/locale/timezone fingerprint rotation
- WebDriver/plugin/Chrome runtime property masking
- Cookie loading from Netscape or JSON format files
- Proxy rotation with success/failure tracking

### 3.11 Prompt Injection Defenses

`sanitize()` detects and strips:
- "Ignore previous instructions"
- "You are now..." / "New persona"
- "System prompt:"
- "Forget everything"
- `[INST]` / `[/INST]` markers
- "Disregard all previous"
- "Act as an unrestricted"
- "Do not follow"
- Known jailbreak prefixes (DAN, etc.)

---

## 4. Framework Integrations

| Framework | File | Tools Exposed |
|---|---|---|
| **LangChain** | `integrations/langchain/tools.py` | `agentfetch_scrape`, `agentfetch_search`, `agentfetch_crawl`, `agentfetch_status` |
| **LlamaIndex** | `integrations/llamaindex/tools.py` | `scrape`, `search`, `crawl`, `status` |
| **CrewAI** | `integrations/crewai/tools.py` | `scrape_tool`, `search_tool`, `crawl_tool`, `status_tool` |
| **OpenAI** | `integrations/openai/tools.py` | `get_tools()` → 4 JSON definitions, `handle_tool_call(name, args)` |
| **Ollama** | `integrations/ollama/tools.py` | `ollama_extract(url, schema)`, `ollama_analyze(content, instruction)` |
| **MCP stdio** | `mcp_server/stdio.py` | `agent_scrape`, `agent_crawl`, `agent_search`, `agent_extract`, `agent_status` |
| **MCP SSE** | `mcp_server/sse.py` | Same 5 tools over SSE transport |
| **REST API** | `api/app.py` + `api/routes.py` | FastAPI with `/scrape`, `/search`, `/crawl`, `/status` endpoints |

### CLI Entry Points

| Command | Entry Point |
|---|---|
| `agentfetch` | FastAPI CLI (`uvicorn`-based REST server) |
| `agentfetch-mcp` | MCP stdio server |

---

## 5. REST API

**`api/routes.py`** — FastAPI routes:

| Method | Path | Description |
|---|---|---|
| POST | `/scrape` | Single URL scrape |
| POST | `/search` | Search + scrape results |
| POST | `/crawl` | Start multi-page crawl job |
| GET | `/crawl/{job_id}` | Poll crawl status/results |
| GET | `/health` | Health check |

All endpoints accept `ScrapeConfig`-equivalent JSON bodies. The `/crawl` endpoint uses a job queue backed by Redis (optional, falls back to in-memory).

---

## 6. What Was Added (Feature Set)

The following features were built on top of the original codebase:

| Feature | Files | Description |
|---|---|---|
| **Category-based routing** | `router.py:746-757`, `searchengine.py:33-39` | `CATEGORY_ROUTES` + engine overrides + `CATEGORY_QUERY_MODIFIERS` |
| **Highlights extraction** | `extractor.py:24-36`, `schema.py:43` | `extract_highlights()` wired into `_apply_post_extraction()` |
| **Structured output schema** | `extractor.py:39-95`, `schema.py:21,44` | `extract_structured()` → `extract_by_schema()` with type coercion |
| **Deep search** | `searchengine.py:42-50` | `generate_query_variations()` → used in `parallel_search()` when `depth="deep"` |
| **Streaming search** | `searchengine.py:453-478` | `stream_search()` async generator |
| **Exports** | `__init__.py` (top-level + core) | All 5 features exported |
| **Bug fixes** | `router.py`, `extractor.py` | See section 8 |

---

## 7. Test Suite

**138 pytest tests** across 9 test files + 4 manual integration scripts:

| File | Tests | Focus |
|---|---|---|
| `tests/test_router.py` | 20 | Fetch routing, cache, categories, fallback |
| `tests/test_searchengine.py` | 30 | Search engines, parallel, stream, deep |
| `tests/test_extractor.py` | 22 | Content extraction, highlights, structured |
| `tests/test_schema.py` | 16 | Pydantic model serialization |
| `tests/test_sanitizer.py` | 13 | Injection detection |
| `tests/test_normalizer.py` | 8 | URL normalization, simhash |
| `tests/test_proxymanager.py` | 7 | Proxy rotation |
| `tests/test_robotstxt.py` | 7 | robots.txt parsing |
| `tests/test_job_queue.py` | 5 | Redis / in-memory queue |

**Manual integration scripts** (root-level):
- `test_hn_all_features.py` — 15 async tests hitting HN with every feature
- `test_comprehensive.py` — All public methods end-to-end
- `test_hn_scrape.py` — Basic HN fetch + search
- `test_hn_deep.py` — HN individual posts + user pages

---

## 8. Bugs Fixed

### Bug 1: Post-Extraction Skipped with `engine="static"` + `use_cache=False`
**File**: `router.py:822-838`  
**Root cause**: `_quality_and_cache()` (which calls `_apply_post_extraction()`) was gated behind `if use_cache:`. With `use_cache=False`, highlights/schema extraction was silently skipped.  
**Fix**: Removed all `if use_cache:` guards. `_quality_and_cache()` now always runs post-extraction. Cache-put behavior is controlled by a `do_cache` parameter.

### Bug 2: Cache Key Ignored Config Differences
**File**: `router.py:778-782`  
**Root cause**: Cache key was just the URL. `smart_fetch(url, config=ScrapeConfig(extract_highlights=True))` after a prior call without highlights returned the stale cached result.  
**Fix**: Added `_cache_key(url, config)` that includes `extract_highlights` and `output_schema` hash. Cache-hit path also re-applies `_apply_post_extraction` with the current config.

### Bug 3: Number Extraction Picked First Number Greedily
**File**: `extractor.py:68-76`  
**Root cause**: `re.findall(r"[\d,]+...", line)[0]` always returned the first number in the line, ignoring semantic context. "$500 million" in the same line as "1500 employees" caused all fields to return 500. Multiplier words ("million", "b") were detected anywhere in the text, not just adjacent to digits.  
**Fix**: Rewrote `_parse_number_value()` with regex patterns that only match adjacent number+multiplier pairs, and proximity scoring that prefers numbers closest to the field name/description words.

---

## 9. Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `AGENTFETCH_STATIC_TIMEOUT` | 15 | HTTP request timeout (seconds) |
| `AGENTFETCH_BROWSER_TIMEOUT` | 30 | Playwright navigation timeout |
| `AGENTFETCH_MAX_RETRIES` | 2 | Retry attempts per fetch |
| `AGENTFETCH_DOMAIN_DELAY` | 0.5 | Delay between same-domain requests |
| `AGENTFETCH_ROBOTS_CHECK` | false | Enable robots.txt compliance |
| `AGENTFETCH_CACHE_SIZE` | 100 | Max cached entries |
| `AGENTFETCH_CACHE_TTL` | 300 | Cache TTL (seconds) |
| `AGENTFETCH_MIN_PROSE_RATIO` | 0.4 | Minimum alpha/total char ratio |
| `AGENTFETCH_MIN_WORDS` | 10 | Minimum word count for valid content |
| `AGENTFETCH_JA3_PROFILE` | (random) | curl_cffi TLS fingerprint profile |
| `AGENTFETCH_STEALTH` | true | Enable playwright-stealth |
| `AGENTFETCH_STEALTH_BASIC_FALLBACK` | true | Fallback to basic browser |
| `AGENTFETCH_COOKIES_FILE` | "" | Path to cookies file |
| `AGENTFETCH_SEARCH_RETRIES` | 2 | Search retry attempts |
| `AGENTFETCH_SEARCH_TIMEOUT` | 15 | Search request timeout |
| `SEARXNG_URL` | "" | Self-hosted SearXNG instance URL |
| `BRAVE_SEARCH_API_KEY` | "" | Brave Search API key |
| `SERPAPI_KEY` | "" | SerpAPI key |
| `GOOGLE_API_KEY` | "" | Google Custom Search API key |
| `GOOGLE_CX` | "" | Google Custom Search CX |

---

## 10. Performance Characteristics

Measured on HN front page (`news.ycombinator.com`):

| Operation | Latency | Notes |
|---|---|---|
| `smart_fetch` (static) | 2-4s | Includes HTTP + extraction |
| `batch_fetch` (2 URLs) | 3-4s | Concurrent with semaphore |
| `parallel_search` (DDG) | 1-3s | Single engine |
| `parallel_search` (deep) | 2-4s | 3-4 query variations |
| `stream_search` | 0.6-2s | First result in <1s |
| `search_fetch` | 0.5-6s | Search + scrape each result |
| `extract_highlights` | <1ms | Pure Python TF scoring |
| `extract_structured` | <1ms | Regex + proximity matching |
