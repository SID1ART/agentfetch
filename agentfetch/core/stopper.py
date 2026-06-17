import logging
from collections import defaultdict

from .normalizer import (
    normalize_url,
    simhash_fingerprint,
    is_near_duplicate,
    extract_domain,
    is_navigation_path,
)

logger = logging.getLogger("agentfetch.stopper")


class CrawlStopper:
    def __init__(self, query: str, threshold: float = 0.82, max_pages: int = 50):
        self.query = query
        self.threshold = threshold
        self.max_pages = max_pages
        self._pages: list[str] = []
        self._fingerprints: list[int] = []
        self._seen_urls: set[str] = set()
        self._seen_norm_urls: set[str] = set()
        self._domain_counts: defaultdict[str, int] = defaultdict(int)
        self._stop_reason: str = ""
        self.duplicates_skipped: int = 0
        self.navigation_paths_skipped: int = 0

    def _fingerprint(self, content: str) -> int:
        return simhash_fingerprint(content)

    def is_url_seen(self, url: str) -> bool:
        norm = normalize_url(url)
        if norm in self._seen_norm_urls:
            return True
        if url in self._seen_urls:
            return True
        return False

    def mark_url_seen(self, url: str) -> None:
        self._seen_urls.add(url)
        self._seen_norm_urls.add(normalize_url(url))

    def is_duplicate_content(self, content: str) -> tuple[bool, float]:
        if not content.strip():
            return True, 0.0
        fp = self._fingerprint(content)
        return is_near_duplicate(fp, self._fingerprints)

    def domain_count(self, url: str) -> int:
        return self._domain_counts.get(extract_domain(url), 0)

    def is_navigation(self, url: str) -> bool:
        from urllib.parse import urlparse

        path = urlparse(url).path
        return is_navigation_path(path)

    def add_page(self, content: str) -> None:
        self._pages.append(content)
        fp = self._fingerprint(content)
        self._fingerprints.append(fp)

    def should_stop(self) -> tuple[bool, str]:
        n = len(self._pages)
        if n >= self.max_pages:
            self._stop_reason = "limit"
            logger.info("Stopping: reached max_pages=%d", self.max_pages)
            return True, "limit"

        if n >= 2:
            last_page = self._pages[-1]
            all_words = set()
            for p in self._pages[:-1]:
                all_words.update(p.lower().split())
            last_words = set(last_page.lower().split())
            total_unique = len(all_words | last_words)
            if total_unique > 0:
                saturation = len(last_words - all_words) / total_unique
                if saturation < 0.05:
                    self._stop_reason = "saturation"
                    logger.info("Stopping: saturation=%.4f < 0.05", saturation)
                    return True, "saturation"

        if n >= 3:
            last_page = self._pages[-1]
            sentences = [s for s in last_page.split(".") if s.strip()]
            if sentences:
                prior_text = " ".join(self._pages[:-1])
                duplicates = sum(1 for s in sentences if s.strip() in prior_text)
                redundancy = duplicates / len(sentences)
                if redundancy > 0.7:
                    self._stop_reason = "saturation"
                    logger.info("Stopping: redundancy=%.4f > 0.7", redundancy)
                    return True, "saturation"

        return False, ""

    def get_stats(self) -> dict:
        unique_words = set()
        for p in self._pages:
            unique_words.update(p.lower().split())
        return {
            "pages_processed": len(self._pages),
            "unique_words": len(unique_words),
            "seen_urls": len(self._seen_urls),
            "duplicates_skipped": self.duplicates_skipped,
            "navigation_paths_skipped": self.navigation_paths_skipped,
            "stop_reason": self._stop_reason,
        }
