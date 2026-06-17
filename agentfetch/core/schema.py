from pydantic import BaseModel, Field
from typing import Optional


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


class CrawlResult(BaseModel):
    job_id: str
    status: str = "pending"
    pages: list[FetchResult] = Field(default_factory=list)
    total_pages: int = 0
    stopped_reason: Optional[str] = None


class SearchResult(BaseModel):
    query: str
    results: list[FetchResult] = Field(default_factory=list)
    source: str = "duckduckgo"
