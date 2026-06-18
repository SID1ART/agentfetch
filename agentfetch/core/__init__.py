from .schema import FetchResult, CrawlResult, SearchResult, SearchConfig, ScrapeConfig
from .router import smart_fetch, batch_fetch
from .searchengine import (
    parallel_search,
    search_fetch,
    stream_search,
    EngineResult,
    _configure_searxng,
)
from .extractor import (
    extract_content,
    detect_content_type,
    extract_highlights,
    extract_structured,
)
from .sanitizer import sanitize
from .stopper import CrawlStopper
from .normalizer import (
    normalize_url,
    content_hash,
    is_near_duplicate,
    simhash_fingerprint,
)
from .robotstxt import RobotsChecker
from .proxymanager import ProxyManager

__all__ = [
    "FetchResult",
    "CrawlResult",
    "SearchResult",
    "SearchConfig",
    "ScrapeConfig",
    "smart_fetch",
    "batch_fetch",
    "parallel_search",
    "search_fetch",
    "stream_search",
    "EngineResult",
    "extract_content",
    "detect_content_type",
    "extract_highlights",
    "extract_structured",
    "sanitize",
    "CrawlStopper",
    "normalize_url",
    "content_hash",
    "is_near_duplicate",
    "simhash_fingerprint",
    "RobotsChecker",
    "ProxyManager",
]
