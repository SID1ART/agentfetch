import logging

logger = logging.getLogger("agentfetch.stopper")


class CrawlStopper:
    def __init__(self, query: str, threshold: float = 0.82, max_pages: int = 50):
        self.query = query
        self.threshold = threshold
        self.max_pages = max_pages
        self._pages: list[str] = []
        self._stop_reason: str = ""

    def add_page(self, content: str) -> None:
        self._pages.append(content)

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
            "stop_reason": self._stop_reason,
        }
