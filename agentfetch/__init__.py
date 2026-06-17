from .core.router import smart_fetch, batch_fetch
from .core.searchengine import parallel_search, search_fetch, _configure_searxng
from .core.schema import (
    FetchResult,
    CrawlResult,
    SearchResult,
    SearchConfig,
    ScrapeConfig,
)
from .core.sanitizer import sanitize
from .core.stopper import CrawlStopper
from .core.extractor import extract_content, detect_content_type

__all__ = [
    "smart_fetch",
    "batch_fetch",
    "parallel_search",
    "search_fetch",
    "FetchResult",
    "CrawlResult",
    "SearchResult",
    "SearchConfig",
    "ScrapeConfig",
    "sanitize",
    "CrawlStopper",
    "extract_content",
    "detect_content_type",
]
