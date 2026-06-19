from typing import Literal, Optional

from pydantic import BaseModel, Field


ActionType = Literal["click", "scroll", "type", "wait", "press", "select", "screenshot"]


class Action(BaseModel):
    type: ActionType
    selector: Optional[str] = None
    value: Optional[str] = None
    timeout: int = 5000


class ScrapeConfig(BaseModel):
    wait_for: Optional[str] = None
    include_tags: Optional[list[str]] = None
    exclude_tags: Optional[list[str]] = None
    viewport: Optional[dict] = None
    js_wait_ms: int = 0
    scrape_links: bool = True
    max_content_length: int = 50000
    citation_links: bool = False
    proxy: Optional[str] = None
    cookies: Optional[list[dict]] = None
    headers: Optional[dict[str, str]] = None
    ja3: Optional[str] = None
    stealth: bool = True
    category: str = "auto"
    extract_highlights: bool = False
    output_schema: Optional[dict] = None
    actions: list[Action] = Field(default_factory=list)
    screenshot: bool = False


class FetchResult(BaseModel):
    url: str
    content: str
    title: Optional[str] = None
    confidence: float
    content_type: str = "unknown"
    word_count: int = 0
    render_mode: str = "static"
    latency_ms: int = 0
    cached: bool = False
    injection_detected: bool = False
    links: Optional[list[str]] = None
    error: Optional[str] = None
    duplicate_of: Optional[str] = None
    retries: int = 0
    normalized_url: Optional[str] = None
    citations: Optional[list[str]] = None
    robots_allowed: bool = True
    proxy_used: Optional[str] = None
    highlights: Optional[list[str]] = None
    structured_output: Optional[dict] = None
    screenshot_data: Optional[str] = None


class CrawlResult(BaseModel):
    job_id: str
    status: str = "pending"
    pages: list[FetchResult] = Field(default_factory=list)
    total_pages: int = 0
    unique_pages: int = 0
    duplicates_skipped: int = 0
    stopped_reason: Optional[str] = None
    queued: bool = False


class SearchConfig(BaseModel):
    max_results: int = 5
    sources: Optional[list[str]] = None
    scrape_results: bool = True
    searxng_url: str = ""
    proxy: Optional[str] = None
    category: str = "auto"
    depth: str = "auto"


class SearchResult(BaseModel):
    query: str
    results: list[FetchResult] = Field(default_factory=list)
    source: str = "duckduckgo"
    sources_used: list[str] = Field(default_factory=list)
    suggestions: Optional[list[str]] = None
    total_results: int = 0
    errors: dict[str, str] = Field(default_factory=dict)
