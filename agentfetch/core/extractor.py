import re
import logging
import json
from urllib.parse import urlparse
from typing import Optional
from collections import Counter

from markdownify import markdownify as md

from .schema import ScrapeConfig

logger = logging.getLogger("agentfetch.extractor")

_HIGHLIGHT_SENTENCES = 5


def _score_sentence(sent: str, word_freq: Counter) -> float:
    words = re.findall(r"\w+", sent.lower())
    if not words:
        return 0.0
    return sum(word_freq.get(w, 0) for w in words) / len(words)


def extract_highlights(
    text: str, max_sentences: int = _HIGHLIGHT_SENTENCES
) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    if len(sentences) <= max_sentences:
        return [s.strip() for s in sentences if len(s.strip()) > 20]

    words = re.findall(r"\w+", text.lower())
    word_freq = Counter(words)
    scored = [(i, _score_sentence(s, word_freq), s) for i, s in enumerate(sentences)]
    top = sorted(scored, key=lambda x: -x[1])[:max_sentences]
    top.sort(key=lambda x: x[0])
    return [s.strip() for _, _, s in top]


def _resolve_field_schema(field_schema):
    if isinstance(field_schema, str):
        return {"type": "string", "description": field_schema}
    return field_schema


def extract_by_schema(text: str, schema: dict) -> dict:
    result = {}
    props = schema.get("properties", {}) if schema.get("type") == "object" else schema
    if isinstance(props, dict):
        for field_name, field_schema in props.items():
            field_schema = _resolve_field_schema(field_schema)
            field_type = field_schema.get("type", "string")
            description = field_schema.get("description", "")
            lines = text.split("\n")
            candidates = []
            for line in lines:
                line = line.strip()
                if not line or len(line) > 200:
                    continue
                lower = line.lower()
                if description and description.lower() in lower:
                    candidates.append(line)
                if field_name.lower().replace("_", " ") in lower:
                    candidates.append(line)
            if candidates:
                best = max(candidates, key=len)
                if field_type == "string":
                    result[field_name] = best
                elif field_type in ("number", "integer"):
                    nums = re.findall(
                        r"[\d,]+(?:\.\d+)?",
                        best.replace("$", "").replace("€", "").replace("£", ""),
                    )
                    if nums:
                        raw = nums[0].replace(",", "")
                        result[field_name] = (
                            int(raw) if field_type == "integer" else float(raw)
                        )
                elif field_type == "boolean":
                    val = (
                        best.split(":", 1)[-1].split("=", 1)[-1].strip()
                        if ":" in best or "=" in best
                        else best
                    )
                    result[field_name] = val.lower() in ("true", "yes", "1", "y")
            else:
                result[field_name] = None
    return result


def extract_structured(text: str, schema: dict) -> Optional[dict]:
    try:
        return extract_by_schema(text, schema)
    except Exception as e:
        logger.warning("Structured extraction failed: %s", e)
        return None


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
