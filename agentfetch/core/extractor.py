import re
import logging
from urllib.parse import urlparse
from typing import Optional

from markdownify import markdownify as md

from .schema import ScrapeConfig

logger = logging.getLogger("agentfetch.extractor")


def extract_content(
    html: str,
    url: str = "",
    config: Optional[ScrapeConfig] = None,
) -> tuple[str, str, list[str]]:
    extractor_name = ""
    text = ""
    config = config or ScrapeConfig()

    if config.include_tags or config.exclude_tags:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        if config.exclude_tags:
            for tag in config.exclude_tags:
                for el in soup.find_all(tag):
                    el.decompose()
        if config.include_tags:
            parts = []
            for tag in config.include_tags:
                for el in soup.find_all(tag):
                    t = el.get_text(strip=True)
                    if t:
                        parts.append(t)
            text = "\n\n".join(parts)
        else:
            parts = []
            for tag in soup.find_all(["p", "article", "section", "main"]):
                t = tag.get_text(strip=True)
                if t:
                    parts.append(t)
            text = "\n\n".join(parts)
        if text:
            extractor_name = "bs4_filtered"
        return _finish_extraction(text, config)

    try:
        import trafilatura

        text = trafilatura.extract(html, include_links=True, include_images=False)
        if text:
            extractor_name = "trafilatura"
            logger.info("Extraction succeeded: %s for %s", extractor_name, url)
    except Exception as e:
        logger.warning("trafilatura failed for %s: %s", url, e)

    if not text:
        try:
            from newspaper import Article

            article = Article(url)
            article.set_html(html)
            article.parse()
            text = article.text
            if text:
                extractor_name = "newspaper3k"
                logger.info("Extraction succeeded: %s for %s", extractor_name, url)
        except Exception as e:
            logger.warning("newspaper3k failed for %s: %s", url, e)

    if not text:
        try:
            from readability import Document

            doc = Document(html)
            text = doc.summary()
            if text:
                extractor_name = "readability"
                logger.info("Extraction succeeded: %s for %s", extractor_name, url)
        except Exception as e:
            logger.warning("readability failed for %s: %s", url, e)

    if not text:
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")

            if config.exclude_tags:
                for tag in config.exclude_tags:
                    for el in soup.find_all(tag):
                        el.decompose()

            if config.include_tags:
                parts = []
                for tag in config.include_tags:
                    for el in soup.find_all(tag):
                        t = el.get_text(strip=True)
                        if t:
                            parts.append(t)
                text = "\n\n".join(parts)
            else:
                parts = []
                for tag in soup.find_all(["p", "article"]):
                    t = tag.get_text(strip=True)
                    if t:
                        parts.append(t)
                text = "\n\n".join(parts)

            if text:
                extractor_name = "bs4"
                logger.info("Extraction succeeded: %s for %s", extractor_name, url)
        except Exception as e:
            logger.warning("bs4 fallback failed for %s: %s", url, e)

    if not text:
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(separator="\n", strip=True)
            extractor_name = "plaintext"
            logger.info("Extraction succeeded: %s for %s", extractor_name, url)
        except Exception as e:
            logger.warning("plaintext fallback failed for %s: %s", url, e)

    citations = []
    if config.citation_links:
        text, citations = _add_citation_markers(text)

    if config.max_content_length and len(text) > config.max_content_length:
        text = text[: config.max_content_length]

    markdown_text = md(text) if text else ""
    return markdown_text, extractor_name, citations


def _finish_extraction(text: str, config: ScrapeConfig) -> tuple[str, str, list[str]]:
    citations = []
    if config.citation_links:
        text, citations = _add_citation_markers(text)
    if config.max_content_length and len(text) > config.max_content_length:
        text = text[: config.max_content_length]
    markdown_text = md(text) if text else ""
    return markdown_text, "", citations


def _add_citation_markers(text: str) -> tuple[str, list[str]]:
    url_pattern = re.compile(r"https?://[^\s)]+")
    urls = url_pattern.findall(text)
    seen: list[str] = []
    citation_map: dict[str, int] = {}

    for u in urls:
        clean = u.rstrip(".,;:!?")
        if clean not in citation_map and len(seen) < 20:
            citation_map[clean] = len(seen) + 1
            seen.append(clean)

    if not seen:
        return text, []

    def _replacer(m: re.Match) -> str:
        raw = m.group(0)
        clean = raw.rstrip(".,;:!?")
        idx = citation_map.get(clean)
        if idx is not None:
            return f"[{idx}]"
        return raw

    result = url_pattern.sub(_replacer, text)
    return result, seen


def detect_content_type(html: str, url: str) -> str:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        og_type = soup.find("meta", property="og:type")
        if og_type and og_type.get("content"):
            ct = og_type["content"].lower()
            if ct in ("article", "website"):
                return "article"
    except Exception:
        pass

    path = urlparse(url).path.lower()
    if any(p in path for p in ("/blog/", "/news/", "/article/")):
        return "article"
    if any(p in path for p in ("/docs/", "/documentation/", "/guide/")):
        return "docs"
    if any(p in path for p in ("/product/", "/item/", "/dp/", "/p/")):
        return "product"
    if any(p in path for p in ("/shop/", "/category/", "/listing/")):
        return "listing"

    price_pattern = r"[$€£]\s*\d+"
    if re.search(price_pattern, html[:5000]):
        return "product"

    return "unknown"
