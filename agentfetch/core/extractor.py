import re
import logging
from urllib.parse import urlparse

from markdownify import markdownify as md

logger = logging.getLogger("agentfetch.extractor")


def extract_content(html: str, url: str = "") -> tuple[str, str]:
    extractor_name = ""
    text = ""

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

    markdown_text = md(text) if text else ""
    return markdown_text, extractor_name


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
